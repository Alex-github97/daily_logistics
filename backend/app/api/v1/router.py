"""
Rutas que expone Daily Logistics.

El código del servidor es el mismo de la plataforma madre, pero aquí solo se
publican los módulos que vende esta herramienta —WMS, POS y TMS— más lo que
necesitan para funcionar: acceso, administración de la empresa, la consola del
operador y las pocas rutas de apoyo que sus pantallas consultan.
"""
from fastapi import APIRouter
from app.api.v1.endpoints import (
    # Acceso y administración de la empresa
    auth, usuarios, roles, alertas, proveedores, catalogos, scan_sessions, configuracion,
    # Consola del operador (usuarios maestros, empresas, módulos)
    plataforma, plataforma_comercial, plataforma_contable, plataforma_equipo,
    soporte, soporte_agil, gestion, gestion_incidencias,
    gestion_consultas, gestion_agil, gestion_pizarras, gestion_config, gestion_formulario,
    # WMS
    wms, wms_codigos, wms_estados_oc, wms_trazable, wms_cubicaje, wms_indicadores, wms_sugerencias,
    wms_maquila, wms_mapa, wms_layout, wms_3pl, wms_traslados, wms_portal, canales, capacidad_carga, wms_documentos,
    # TMS
    tms, tms_conductores, fletes,
    # POS
    pos,
    # Apoyo: conductores (TMS), vehículos (TMS) y resoluciones DIAN (POS)
    hcm, eam, erp_facturacion,
)

api_router = APIRouter()

api_router.include_router(auth.router)
# Consola del operador: administra OTRAS empresas, no la propia.
api_router.include_router(plataforma.router)
api_router.include_router(plataforma_comercial.router)
api_router.include_router(plataforma_contable.router)
api_router.include_router(plataforma_equipo.router)
# Mesa de ayuda: el cliente escribe, soporte responde desde la consola.
api_router.include_router(soporte.router)
api_router.include_router(soporte_agil.router)
# Un ticket de soporte puede volverse incidencia de gestión.
api_router.include_router(gestion.router)
api_router.include_router(gestion_incidencias.router)
# Proyectos de la consola: consultas guardadas, ágil (sprints, backlog),
# pizarras, configuración de campos/flujos y formularios.
api_router.include_router(gestion_consultas.router)
api_router.include_router(gestion_agil.router)
api_router.include_router(gestion_pizarras.router)
api_router.include_router(gestion_config.router)
api_router.include_router(gestion_formulario.router)

api_router.include_router(roles.router)
# Configuración general: datos de la empresa y estado de la puesta en marcha.
api_router.include_router(configuracion.router)
api_router.include_router(usuarios.router)
api_router.include_router(alertas.router)
api_router.include_router(proveedores.router)
api_router.include_router(catalogos.router)
api_router.include_router(scan_sessions.router)

# Maestro de productos y escaneo: antes que wms para que /wms/maestro y
# /wms/codigos no los tome una ruta más general.
api_router.include_router(wms_codigos.router)
api_router.include_router(canales.router)
api_router.include_router(capacidad_carga.router)
api_router.include_router(wms_documentos.router)
# Estados configurables de la orden de compra.
api_router.include_router(wms_estados_oc.router)
api_router.include_router(wms.router)
api_router.include_router(wms_trazable.router)
api_router.include_router(wms_cubicaje.router)
api_router.include_router(wms_indicadores.router)
api_router.include_router(wms_sugerencias.router)
api_router.include_router(wms_maquila.router)
api_router.include_router(wms_mapa.router)
api_router.include_router(wms_layout.router)
api_router.include_router(wms_3pl.router)
api_router.include_router(wms_traslados.router)
api_router.include_router(wms_portal.router)

api_router.include_router(tms.router)
# Conductores creados desde el TMS (Daily Logistics no tiene Gestión Humana).
api_router.include_router(tms_conductores.router)
api_router.include_router(fletes.router)

api_router.include_router(pos.router)

api_router.include_router(hcm.router)
api_router.include_router(eam.router)
api_router.include_router(erp_facturacion.router)
