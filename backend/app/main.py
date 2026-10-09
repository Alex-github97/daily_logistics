from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import json
import os
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.tenant import ESQUEMA_POR_DEFECTO
from app.infrastructure.models.gestion import TIPOS_DE_ENTIDAD
from app.core.middleware_tenant import TenantMiddleware
from app.core.acceso_modulos import ModulosMiddleware
from app.core.auth_global import exigir_sesion
from app.api.v1.router import api_router
import app.infrastructure.models  # noqa: F401 — registra todos los modelos
import app.core.marketplace.trabajador  # noqa: F401 — anota cambios de stock para los canales de venta
import app.core.wms_estados_linea  # noqa: F401 — estado de cada línea de la orden de salida según sus cantidades
from app.core.semillas_lubricacion import sembrar_lubricacion
from app.infrastructure.models.rol import Rol, ROLES_DEFECTO
from app.infrastructure.models.usuario import Usuario

# Catálogo estándar de esquemas de ejes/llantas (referencia de la industria del
# transporte de carga). `layout` = cantidad de llantas por cada eje, en orden.
ESQUEMAS_VEHICULO_SEED = """
                ('esq1_2', '2 Ejes, 4 llantas tracción 4 Ruedas (4WD)', 2, '[2, 2]'::json, false, 0, true, now(), now()),
                ('esq1', '2 Ejes, 4 llantas tracción delantera (FWD)', 2, '[2, 2]'::json, false, 0, true, now(), now()),
                ('esq1_1', '2 Ejes, 4 llantas tracción trasera (RWD)', 2, '[2, 2]'::json, false, 0, true, now(), now()),
                ('esq1_3', '2 Ejes, 4 llantas, tracción delantera, dirección trasera', 2, '[2, 2]'::json, false, 0, true, now(), now()),
                ('esq2', '2 Ejes, 6 Llantas', 2, '[2, 4]'::json, false, 0, true, now(), now()),
                ('esq38', '2 Ejes, 6 llantas dirección trasera', 2, '[4, 2]'::json, false, 0, true, now(), now()),
                ('esq4', '3 Ejes, 10 Llantas', 3, '[2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq3', '3 Ejes, 6 Llantas', 3, '[2, 2, 2]'::json, false, 0, true, now(), now()),
                ('esq35', '3 Ejes, 8 Llantas', 3, '[2, 2, 4]'::json, false, 0, true, now(), now()),
                ('esq28', '5 ejes 10 llantas', 5, '[2, 2, 2, 2, 2]'::json, false, 0, true, now(), now()),
                ('esq26', 'Articulado 3 ejes 10 llantas', 3, '[2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq27', 'Biarticulado 4 ejes 14 llantas', 4, '[2, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq31', 'Bus 3 ejes, 8 Llantas', 3, '[2, 2, 4]'::json, false, 0, true, now(), now()),
                ('esq52', 'Bus 4 ejes, 10 llantas', 4, '[2, 2, 2, 4]'::json, false, 0, true, now(), now()),
                ('esq47', 'Cabezote 2 Ejes + Trailer 2 Ejes + Trailer 2 Ejes + Trailer 2 Ejes, 30 llantas', 8, '[2, 4, 4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq42', 'Cabezote 2 Ejes + Trailer 2 Ejes, 10 llantas', 4, '[2, 2, 2, 4]'::json, false, 0, true, now(), now()),
                ('esq10', 'Cabezote 2 Ejes + Trailer 2 Ejes, 14 llantas', 4, '[2, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq11', 'Cabezote 2 Ejes + Trailer 3 Ejes, 18 llantas', 5, '[2, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq48', 'Cabezote 3 Ejes + Trailer 2 Ejes + Trailer 2 Ejes + Trailer 2 Ejes, 34 llantas', 9, '[2, 4, 4, 4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq18', 'Cabezote 3 Ejes + Trailer 2 Ejes, 14 llantas', 5, '[2, 3, 3, 3, 3]'::json, false, 0, true, now(), now()),
                ('esq8', 'Cabezote 3 Ejes + Trailer 2 Ejes, 18 llantas', 5, '[2, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq20', 'Cabezote 3 Ejes + Trailer 3 Ejes, 16 llantas', 6, '[2, 2, 2, 2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq9', 'Cabezote 3 Ejes + Trailer 3 Ejes, 22 llantas', 6, '[2, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq17', 'Cabezote 3 Ejes + Trailer 4 Ejes, 26 llantas', 7, '[2, 4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq45', 'Cabezote 3 Ejes + Trailer 5 Ejes, 30 llantas', 8, '[2, 4, 4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq43', 'Cabezote 3 Ejes + Trailer 6 Ejes, 34 llantas', 9, '[2, 4, 4, 4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq44', 'Cabezote 3 ejes, 8 llantas', 3, '[2, 2, 4]'::json, false, 0, true, now(), now()),
                ('esq7', 'Cuatro Direccionales 4 Ejes, 12 Llantas', 4, '[2, 2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq41', 'Grúa 4 ejes, 8 llantas', 4, '[2, 2, 2, 2]'::json, false, 0, true, now(), now()),
                ('esq49', 'Grúa 5 ejes, 14 llantas', 5, '[2, 2, 2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq50', 'Grúa 6 ejes, 18 llantas', 6, '[2, 2, 2, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq22', 'Mixer 4 Ejes, 12 Llantas', 4, '[2, 2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq23', 'Mixer 4 Ejes, 14 Llantas', 4, '[2, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq12', 'Moto 2 Ejes, 2 llantas', 2, '[1, 1]'::json, false, 0, true, now(), now()),
                ('esq14', 'Moto 2 Ejes, 3 llantas', 2, '[1, 2]'::json, false, 0, true, now(), now()),
                ('esq40', 'Moto 2 Ejes, 5 llantas', 2, '[1, 4]'::json, false, 0, true, now(), now()),
                ('esq24', 'Trailer 1 Eje, 4 Llantas', 1, '[4]'::json, false, 0, true, now(), now()),
                ('esq32', 'Trailer 2 ejes, 16 Llantas', 2, '[8, 8]'::json, false, 0, true, now(), now()),
                ('esq15', 'Trailer 2 Ejes, 4 Llantas', 2, '[2, 2]'::json, false, 0, true, now(), now()),
                ('esq5', 'Trailer 2 Ejes, 8 Llantas', 2, '[4, 4]'::json, false, 0, true, now(), now()),
                ('esq51', 'Trailer 3 Ejes, 10 Llantas', 3, '[2, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq6', 'Trailer 3 Ejes, 12 Llantas', 3, '[4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq33', 'Trailer 3 ejes, 24 Llantas', 3, '[8, 8, 8]'::json, false, 0, true, now(), now()),
                ('esq16', 'Trailer 3 Ejes, 6 Llantas', 3, '[2, 2, 2]'::json, false, 0, true, now(), now()),
                ('esq13', 'Trailer 4 Ejes 16 llantas', 4, '[4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq25', 'Trailer 4 Ejes 32 llantas', 4, '[8, 8, 8, 8]'::json, false, 0, true, now(), now()),
                ('esq46', 'Trailer 5 Ejes 20 llantas', 5, '[4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq34', 'Trailer 6 ejes, 48 Llantas', 6, '[8, 8, 8, 8, 8, 8]'::json, false, 0, true, now(), now()),
                ('esq29', 'Trailer Cama Baja 5 Ejes, 20 Llantas', 5, '[4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq30', 'Trailer Cama Baja 6 Ejes, 24 Llantas', 6, '[4, 4, 4, 4, 4, 4]'::json, false, 0, true, now(), now()),
                ('esq19', 'Tranvía de 6 ejes, 12 llantas', 6, '[2, 2, 2, 2, 2, 2]'::json, false, 0, true, now(), now()),
                ('esq21', 'Vibrocompactador, Rodillo frontal 2 ruedas traseras', 1, '[2]'::json, false, 0, true, now(), now())
"""


async def _seed_roles_and_migrate(db: AsyncSession) -> None:
    # Sembrar roles por defecto si la tabla está vacía
    # Daily Logistics: los roles por defecto que falten se crean, y a los de
    # sistema se les agregan los permisos que no tengan (wms, tms, pos,
    # usuarios, configuracion). Lo que el administrador ya haya marcado o
    # desmarcado no se toca.
    existentes = {r.nombre: r for r in (await db.execute(select(Rol))).scalars().all()}
    for r in ROLES_DEFECTO:
        rol = existentes.get(r["nombre"])
        if rol is None:
            db.add(Rol(**r))
        elif rol.es_sistema:
            faltan = {k: v for k, v in r["permisos"].items() if k not in (rol.permisos or {})}
            if faltan:
                rol.permisos = {**(rol.permisos or {}), **faltan}
    await db.flush()

    # Construir mapa nombre → id
    roles_result = await db.execute(select(Rol))
    roles_map = {r.nombre: r.id for r in roles_result.scalars().all()}

    # Asignar rol_id a usuarios que aún no lo tienen
    users_result = await db.execute(
        select(Usuario).where(Usuario.rol_id == None, Usuario.activo == True)  # noqa: E711
    )
    for user in users_result.scalars().all():
        # `rol` es una columna de texto: puede venir como str o, si en algún
        # punto se mapeó a enum, con .value. Suponer siempre lo segundo rompía
        # el arranque en cuanto un cliente nuevo tenía un usuario sin rol_id.
        rol = user.rol
        enum_name = getattr(rol, "value", rol) or "CONSULTA"
        if enum_name in roles_map:
            user.rol_id = roles_map[enum_name]


@asynccontextmanager
async def _conexion(esquema: str):
    """Conexión ya apuntando al esquema del cliente, creándolo si hace falta."""
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
        # Solo el esquema del cliente: si "public" quedara detrás, create_all
        # encontraría allí las tablas y no crearía las de este cliente, y un
        # ALTER sin calificar caería sobre las de otro.
        await conn.execute(text(f'SET search_path TO "{esquema}"'))
        yield conn


async def _preparar_registro_clientes() -> None:
    """Pone al día el registro de clientes, que vive fuera de los esquemas."""
    async with engine.begin() as conn:
        await conn.execute(text('SET search_path TO "public"'))
        # Sesiones del celular como escáner. Vivían en un diccionario del
        # proceso; con cuatro workers el código que manda el celular caía en uno
        # y el PC preguntaba en otro, y el escaneo se perdía sin error.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.scan_sesion (
                id        VARCHAR(36) PRIMARY KEY,
                creada    TIMESTAMPTZ NOT NULL DEFAULT now(),
                codigos   JSONB       NOT NULL DEFAULT '[]'::jsonb
            )
        """))
        if (await conn.execute(text("SELECT to_regclass('public.plataforma_cliente')"))).scalar() is None:
            return
        await conn.execute(text(
            "ALTER TABLE public.plataforma_cliente "
            "ADD COLUMN IF NOT EXISTS es_operador BOOLEAN DEFAULT false"
        ))
        # La mesa de ayuda nació sin gestión ágil: estas columnas se agregan
        # sobre los tickets que ya existan.
        if (await conn.execute(
                text("SELECT to_regclass('public.soporte_ticket')"))).scalar() is not None:
            for columna, tipo in (
                ("tipo_trabajo", "VARCHAR(20) DEFAULT 'ERROR'"),
                ("puntos", "INTEGER"),
                ("sprint_id", "INTEGER"),
                ("epica_id", "INTEGER"),
                ("orden", "DOUBLE PRECISION DEFAULT 0"),
                ("etiquetas", "JSON"),
                ("iniciado_en", "TIMESTAMP"),
            ):
                await conn.execute(text(
                    f"ALTER TABLE public.soporte_ticket "
                    f"ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

        # Los pagos existen desde antes que las facturas: la columna se agrega
        # vacía y esos pagos quedan como anticipos sin factura, que es lo que
        # de hecho son.
        if (await conn.execute(
                text("SELECT to_regclass('public.plataforma_pago')"))).scalar() is not None:
            await conn.execute(text(
                "ALTER TABLE public.plataforma_pago "
                "ADD COLUMN IF NOT EXISTS factura_id INTEGER"
            ))
        # WFM · Personal salió del WMS (las jornadas vivían allí): quien tiene
        # el WMS contratado recibe WFM una sola vez. Si después se le quita, la
        # fila queda inactiva y no se vuelve a agregar.
        if (await conn.execute(text("SELECT to_regclass('public.plataforma_modulo_cliente')"))).scalar():
            await conn.execute(text(
                "INSERT INTO public.plataforma_modulo_cliente (cliente_id, modulo, activo, desde) "
                "SELECT m.cliente_id, 'wfm', true, CURRENT_DATE FROM public.plataforma_modulo_cliente m "
                "WHERE m.modulo = 'wms' AND m.activo AND NOT EXISTS (SELECT 1 FROM public.plataforma_modulo_cliente x "
                "WHERE x.cliente_id = m.cliente_id AND x.modulo = 'wfm')"))
        # Sin operador nadie podría dar de alta empresas: se designa a la que
        # ya estaba, que es la de quien monta la plataforma.
        hay = (await conn.execute(text(
            "SELECT count(*) FROM public.plataforma_cliente WHERE es_operador = true"
        ))).scalar() or 0
        if hay == 0:
            await conn.execute(text(
                "UPDATE public.plataforma_cliente SET es_operador = true "
                "WHERE id = (SELECT MIN(id) FROM public.plataforma_cliente)"
            ))


async def _preparar_gestion() -> None:
    """Lo que `create_all` no sabe construir del módulo de gestión.

    Corre ANTES de `create_all` a propósito: `gp_historial` es una tabla
    particionada, y `create_all` solo sabe crear tablas normales. Si llegara
    primero la crearía sin particiones y ya no habría vuelta atrás sin reescribir
    la tabla entera. Creándola acá, `create_all` la encuentra hecha y no la toca.

    Va particionada por año porque es la que de verdad crece —una veintena de
    filas por cada incidencia, así que va uno o dos órdenes de magnitud por
    encima de las demás— y convertir una tabla grande en particionada obliga a
    copiarla completa. Por año y no por mes para que el mantenimiento sea mínimo,
    y con una partición DEFAULT para que un año sin crear nunca haga fallar una
    inserción: el historial es el camino caliente de todo cambio, y que se caiga
    ahí tumbaría la escritura entera.
    """
    async with engine.begin() as conn:
        await conn.execute(text('SET search_path TO "public"'))
        if (await conn.execute(
                text("SELECT to_regclass('public.gp_historial')"))).scalar() is None:
            await conn.execute(text("""
                CREATE TABLE public.gp_historial (
                    id            BIGINT GENERATED BY DEFAULT AS IDENTITY,
                    incidencia_id BIGINT      NOT NULL,
                    campo         VARCHAR(60) NOT NULL,
                    anterior      VARCHAR(500),
                    nuevo         VARCHAR(500),
                    autor         VARCHAR(80),
                    creado        TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT pk_gp_historial PRIMARY KEY (id, creado)
                ) PARTITION BY RANGE (creado)
            """))
            await conn.execute(text(
                "CREATE INDEX ix_gp_hist_inc ON public.gp_historial "
                "(incidencia_id, creado)"))
            await conn.execute(text(
                "CREATE INDEX ix_gp_hist_fecha ON public.gp_historial (creado)"))

        # Del año pasado a tres adelante. Es idempotente, así que cada arranque
        # va corriendo la ventana sin que nadie tenga que acordarse.
        await conn.execute(text("""
            DO $$
            DECLARE anio int;
                    actual int := EXTRACT(YEAR FROM now())::int;
            BEGIN
                FOR anio IN (actual - 1)..(actual + 3) LOOP
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS public.gp_historial_%s '
                        'PARTITION OF public.gp_historial '
                        'FOR VALUES FROM (%L) TO (%L)',
                        anio, anio || '-01-01', (anio + 1) || '-01-01');
                END LOOP;
            END $$
        """))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS public.gp_historial_resto "
            "PARTITION OF public.gp_historial DEFAULT"))


async def _sembrar_gestion() -> None:
    """El arranque en frío del módulo: un flujo, prioridades, tipos y campos.

    Sin esto, la primera pantalla que se abre pide escoger un workflow de una
    lista vacía y no hay forma de crear nada. Todo lo que se siembra acá es
    editable después: son valores de partida, no constantes del sistema.

    Cada bloque comprueba si ya hay algo antes de insertar. No es solo por los
    reinicios: en producción arrancan cuatro procesos a la vez y, aunque el
    candado de migración los serializa, el que entra segundo tiene que encontrar
    el trabajo hecho y no duplicarlo.
    """
    async with engine.begin() as conn:
        await conn.execute(text('SET search_path TO "public"'))
        if (await conn.execute(
                text("SELECT to_regclass('public.gp_workflow')"))).scalar() is None:
            return

        # `create_all` no altera tablas existentes: las columnas que nacieron
        # después de la tabla se agregan a mano.
        for tabla, columnas in (
            ("gp_campo", (
                ("origen", "VARCHAR(20) DEFAULT 'PROPIO' NOT NULL"),
                ("entidad", "VARCHAR(40)"),
                ("almacenamiento", "VARCHAR(12) DEFAULT 'JSONB' NOT NULL"),
                ("columna", "VARCHAR(40)"),
                ("seccion", "VARCHAR(30) DEFAULT 'DETALLE' NOT NULL"),
                ("orden", "INTEGER DEFAULT 0 NOT NULL"),
            )),
            ("gp_esquema_campo", (
                ("visible", "BOOLEAN DEFAULT true NOT NULL"),
            )),
        ):
            if (await conn.execute(text(
                    f"SELECT to_regclass('public.{tabla}')"))).scalar() is None:
                continue
            for columna, tipo in columnas:
                await conn.execute(text(
                    f"ALTER TABLE public.{tabla} "
                    f"ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

        # ── El flujo por defecto ──
        hay = (await conn.execute(
            text("SELECT count(*) FROM public.gp_workflow"))).scalar() or 0
        if hay == 0:
            wf = (await conn.execute(text(
                "INSERT INTO public.gp_workflow (nombre, descripcion, por_defecto, "
                "archivado, created_at, updated_at) "
                "VALUES ('Flujo estándar', "
                "'De la solicitud sin clasificar hasta hecho.', true, false, "
                "now(), now()) RETURNING id"))).scalar()

            # 'Por clasificar' es el estado inicial y su categoría propia lo
            # excluye del backlog, del tablero y de las métricas de entrega. Es
            # lo que permite que toda solicitud de soporte cree su incidencia
            # automáticamente sin que las consultas que se resuelven en el chat
            # ensucien las cifras.
            estados = (
                ("SIN_CLASIFICAR", "Por clasificar", "SIN_CLASIFICAR", "#8C8C8C", 0, True,  None),
                ("POR_HACER",      "Por hacer",      "POR_HACER",      "#4D4D4D", 1, False, None),
                ("EN_CURSO",       "En curso",       "EN_CURSO",       "#2F6FEB", 2, False, 5),
                ("EN_REVISION",    "En revisión",    "EN_CURSO",       "#7BA4F5", 3, False, 3),
                ("HECHO",          "Hecho",          "TERMINADO",      "#16A34A", 4, False, None),
                ("DESCARTADA",     "Descartada",     "TERMINADO",      "#8C8C8C", 5, False, None),
            )
            ids: dict[str, int] = {}
            for clave, nombre, categoria, color, orden, inicial, wip in estados:
                ids[clave] = (await conn.execute(text(
                    "INSERT INTO public.gp_estado (workflow_id, clave, nombre, "
                    "categoria, color, orden, inicial, limite_wip) "
                    "VALUES (:w, :c, :n, :cat, :col, :o, :i, :wip) RETURNING id"),
                    {"w": wf, "c": clave, "n": nombre, "cat": categoria,
                     "col": color, "o": orden, "i": inicial, "wip": wip})).scalar()

            # Las acciones se nombran por clave y el servidor las resuelve contra
            # su registro de funciones. Nunca se guarda código acá: quien
            # configura un flujo no puede quedar ejecutando lo que quiera dentro
            # del proceso.
            transiciones = (
                ("Clasificar",  ids["SIN_CLASIFICAR"], ids["POR_HACER"],   "[]", 0),
                ("Empezar",     ids["POR_HACER"],      ids["EN_CURSO"],
                 '[{"clave": "sellar_iniciado"}, {"clave": "asignar_a_quien_mueve"}]', 1),
                ("A revisión",  ids["EN_CURSO"],       ids["EN_REVISION"], "[]", 2),
                ("Devolver",    ids["EN_REVISION"],    ids["EN_CURSO"],    "[]", 3),
                ("Terminar",    ids["EN_REVISION"],    ids["HECHO"],
                 '[{"clave": "sellar_resuelto"}]', 4),
                # Sin origen: se puede llegar desde cualquier estado. Es lo que
                # evita declarar una transición de descarte por cada estado.
                ("Descartar",   None,                  ids["DESCARTADA"],
                 '[{"clave": "sellar_resuelto"}]', 5),
            )
            for nombre, origen, destino, acciones, orden in transiciones:
                await conn.execute(text(
                    # CAST y no `:a::jsonb`: el `::` pegado a un parámetro se lo
                    # come el analizador de SQLAlchemy, que lee `:a:` como el
                    # nombre del parámetro y deja la consulta rota.
                    "INSERT INTO public.gp_transicion (workflow_id, nombre, "
                    "origen_id, destino_id, condiciones, validaciones, acciones, "
                    "orden) VALUES (:w, :n, :o, :d, '[]'::jsonb, '[]'::jsonb, "
                    "CAST(:a AS jsonb), :ord)"),
                    {"w": wf, "n": nombre, "o": origen, "d": destino,
                     "a": acciones, "ord": orden})

        # La fecha planeada de inicio nacio despues que la tabla, y
        # `create_all` no altera tablas existentes. Junto con `vence` es la
        # barra del Gantt.
        await conn.execute(text(
            "ALTER TABLE public.gp_incidencia "
            "ADD COLUMN IF NOT EXISTS inicio_plan TIMESTAMPTZ"))

        # ── Prioridades ──
        hay = (await conn.execute(
            text("SELECT count(*) FROM public.gp_prioridad"))).scalar() or 0
        if hay == 0:
            # Orden ascendente = más urgente primero, para poder ordenar una cola
            # sin invertir nada en cada consulta.
            for clave, nombre, color, orden, defecto in (
                ("CRITICA", "Crítica", "#DC2626", 1, False),
                ("ALTA",    "Alta",    "#D97706", 2, False),
                ("MEDIA",   "Media",   "#2F6FEB", 3, True),
                ("BAJA",    "Baja",    "#8C8C8C", 4, False),
            ):
                await conn.execute(text(
                    "INSERT INTO public.gp_prioridad (clave, nombre, color, orden, "
                    "por_defecto) VALUES (:c, :n, :col, :o, :d)"),
                    {"c": clave, "n": nombre, "col": color, "o": orden, "d": defecto})

        # ── Tipos de incidencia ──
        hay = (await conn.execute(
            text("SELECT count(*) FROM public.gp_tipo_incidencia"))).scalar() or 0
        if hay == 0:
            # Globales: sirven a todos los proyectos mientras alguno no defina los
            # suyos. El nivel es lo que le dice al motor qué puede colgar de qué.
            for clave, nombre, icono, color, nivel, orden in (
                ("EPICA",    "Épica",    "◆", "#7C3AED", "EPICA",    0),
                ("ERROR",    "Error",    "●", "#DC2626", "NORMAL",   1),
                ("MEJORA",   "Mejora",   "▲", "#16A34A", "NORMAL",   2),
                ("TAREA",    "Tarea",    "■", "#2F6FEB", "NORMAL",   3),
                ("CONSULTA", "Consulta", "?", "#8C8C8C", "NORMAL",   4),
                ("SUBTAREA", "Subtarea", "▸", "#4D4D4D", "SUBTAREA", 5),
            ):
                await conn.execute(text(
                    "INSERT INTO public.gp_tipo_incidencia (proyecto_id, clave, "
                    "nombre, icono, color, nivel, workflow_id, orden, archivado) "
                    "VALUES (NULL, :c, :n, :i, :col, :niv, NULL, :o, false)"),
                    {"c": clave, "n": nombre, "i": icono, "col": color,
                     "niv": nivel, "o": orden})

        # ── El registro de campos ──
        #
        # Acá entran los DOS tipos: los nativos —que guardan su valor en una
        # columna de `gp_incidencia`— y los configurables —que lo guardan en el
        # jsonb—. Tenerlos en el mismo registro es lo que permite que el
        # formulario se dibuje entero desde la configuración, en vez de tener
        # media pantalla cableada y media dinámica.
        #
        # Se siembran uno por uno y solo si faltan, no «si la tabla está vacía»:
        # de la otra forma, una instalación que ya tenga campos no recibiría
        # nunca los que se agreguen después.
        NATIVOS = [
            # (clave, nombre, tipo, seccion, ayuda, validacion, filtrable,
            #  almacenamiento, columna, del_sistema, defecto, obligatorio)
            ("resumen", "Título", "TEXTO", "PRINCIPAL",
             "Se puede reescribir después, cuantas veces haga falta.",
             {"max": 300}, True, "COLUMNA", "resumen", True, None, True),
            ("descripcion", "Descripción", "TEXTO_RICO", "PRINCIPAL",
             None, {}, False, "COLUMNA", "descripcion", True, None, False),
            ("prioridad", "Prioridad", "PRIORIDAD", "PRINCIPAL",
             None, {}, True, "COLUMNA", "prioridad_id", True, None, False),
            ("asignado", "Responsable", "USUARIO", "PRINCIPAL",
             "Se puede dejar sin asignar.", {}, True, "COLUMNA", "asignado",
             True, None, False),
            ("reporta", "Reportó", "USUARIO", "PRINCIPAL",
             "Cámbielo si la registra a nombre de otro.", {}, True,
             "COLUMNA", "reporta", True, "@yo", False),

            ("padre", "Cuelga de", "EPICA", "AGIL",
             "Una normal cuelga de una épica; una subtarea, de una normal.",
             {}, False, "COLUMNA", "padre_id", True, None, False),
            ("sprint", "Sprint", "SPRINT", "AGIL",
             None, {}, True, "COLUMNA", "sprint_id", True, "@sprint_activo", False),
            ("puntos", "Estimación (puntos)", "NUMERO", "AGIL",
             "Vacío no es cero: cero es «ya estaba hecho».",
             {"min": 0, "max": 100}, True, "COLUMNA", "puntos", True, None, False),

            ("etiquetas", "Etiquetas", "ETIQUETAS", "CLASIFICACION",
             None, {}, False, "COLUMNA", "etiquetas", True, None, False),

            ("inicio_plan", "Inicio previsto", "FECHA", "FECHAS",
             "Con «vence» forma la barra del Gantt.", {}, True,
             "COLUMNA", "inicio_plan", True, None, False),
            ("vence", "Vence", "FECHA", "FECHAS",
             None, {}, True, "COLUMNA", "vence", True, None, False),
        ]

        # Los configurables de arranque. Ninguno es del sistema: se pueden
        # borrar, renombrar o cambiar de sitio. Están para que la pantalla no
        # abra vacía, que es donde la gente concluye que la función no existe.
        CONFIGURABLES = [
            # (clave, nombre, tipo, seccion, ayuda, validacion, filtrable, opciones)
            ("severidad", "Severidad", "LISTA", "CLASIFICACION",
             "Qué tan grave es, con independencia de la prioridad: la prioridad "
             "dice en qué orden se atiende y la severidad cuánto daño hace.",
             {}, True, [("S1", "S1 · Bloqueante"), ("S2", "S2 · Grave"),
                        ("S3", "S3 · Moderada"), ("S4", "S4 · Menor")]),
            ("componente", "Componente", "COMPONENTE", "CLASIFICACION",
             "Qué pieza del producto está implicada.", {}, False, []),
            ("version_afectada", "Versión afectada", "VERSION", "CLASIFICACION",
             "En cuál se vio.", {}, False, []),
            ("version_corrige", "Se corrige en", "VERSION", "CLASIFICACION",
             "En cuál entra la corrección.", {}, False, []),
            ("modulo", "Módulo", "LISTA", "CLASIFICACION",
             "En qué parte de la plataforma ocurre.", {}, True,
             [("EAM", "Mantenimiento"), ("MES", "Producción"), ("WMS", "Almacén"),
              ("TMS", "Transporte"), ("ERP", "Administrativo"), ("HCM", "Personal"),
              ("CRM", "Comercial"), ("OTRO", "Otro")]),
            ("ambiente", "Ambiente", "LISTA", "CLASIFICACION",
             "Dónde se vio. Un fallo en producción no se prioriza como uno en "
             "pruebas.", {}, True,
             [("PRODUCCION", "Producción"), ("PRUEBAS", "Pruebas"),
              ("LOCAL", "Local")]),
            ("equipo", "Equipo", "LISTA", "CLASIFICACION",
             "Qué equipo responde.", {}, True,
             [("PLATAFORMA", "Plataforma"), ("PRODUCTO", "Producto"),
              ("SOPORTE", "Soporte"), ("DATOS", "Datos")]),
            ("empresa_afectada", "Empresa afectada", "TEXTO", "CLASIFICACION",
             "A qué cliente le ocurre.", {"max": 120}, True, []),

            ("pasos_reproducir", "Pasos para reproducir", "TEXTO_LARGO", "DETALLE",
             "Qué hay que hacer, en orden, para que vuelva a pasar. Es lo que "
             "separa un reporte que se puede atender de uno que hay que devolver.",
             {}, False, []),
            ("resultado_esperado", "Qué debería pasar", "TEXTO_LARGO", "DETALLE",
             "Sin esto, «no funciona» no dice qué es funcionar.", {}, False, []),
            ("resultado_actual", "Qué pasa en su lugar", "TEXTO_LARGO", "DETALLE",
             None, {}, False, []),
            ("historia_usuario", "Historia de usuario", "TEXTO_LARGO", "DETALLE",
             "Como <quién> quiero <qué> para <para qué>.", {}, False, []),
            ("criterios_aceptacion", "Criterios de aceptación", "TEXTO_LARGO",
             "DETALLE",
             "Cuándo se considera terminada. Sin esto, «hecho» lo decide quien "
             "lo hizo.", {}, False, []),
            ("url_afectada", "Dónde ocurre", "URL", "DETALLE",
             "La dirección de la pantalla donde pasa.", {}, False, []),

            ("esfuerzo_horas", "Esfuerzo estimado (h)", "DECIMAL", "AVANZADO",
             "Solo para planear capacidad; la estimación relativa son los puntos.",
             {"min": 0, "max": 400, "decimales": 1}, False, []),
            ("contacto", "Contacto del cliente", "CORREO", "AVANZADO",
             "A quién avisar cuando se resuelva.", {}, False, []),
        ]

        async def _sembrar_campo(clave, nombre, tipo, seccion, ayuda, validacion,
                                 filtrable, origen, entidad, almacenamiento,
                                 columna, del_sistema, defecto, obligatorio,
                                 opciones, orden):
            """Da de alta un campo si falta, con su regla de uso y su índice."""
            ya = (await conn.execute(text(
                "SELECT id FROM public.gp_campo WHERE clave = :c"),
                {"c": clave})).scalar()
            if ya is not None:
                return

            campo_id = (await conn.execute(text(
                "INSERT INTO public.gp_campo (clave, nombre, descripcion, ayuda, "
                "tipo, origen, entidad, almacenamiento, columna, seccion, orden, "
                "validacion, valor_defecto, filtrable, ordenable, del_sistema, "
                "archivado, created_at, updated_at) "
                "VALUES (:c, :n, NULL, :a, :t, :ori, :ent, :alm, :col, :sec, :o, "
                "CAST(:v AS jsonb), CAST(:d AS jsonb), :f, :f, :sis, false, "
                "now(), now()) RETURNING id"),
                {"c": clave, "n": nombre, "a": ayuda, "t": tipo, "ori": origen,
                 "ent": entidad, "alm": almacenamiento, "col": columna,
                 "sec": seccion, "o": orden, "v": json.dumps(validacion),
                 "d": json.dumps(defecto) if defecto is not None else None,
                 "f": filtrable, "sis": del_sistema})).scalar()

            for i, (valor, etiqueta) in enumerate(opciones):
                await conn.execute(text(
                    "INSERT INTO public.gp_campo_opcion (campo_id, valor, etiqueta, "
                    "orden, archivada) VALUES (:c, :v, :e, :o, false)"),
                    {"c": campo_id, "v": valor, "e": etiqueta, "o": i})

            # La regla de uso, en el mismo paso. Un campo sin fila en
            # `gp_esquema_campo` existe pero no aplica a nada: sale en la
            # configuracion y en ningun formulario, y nadie lo descubre hasta que
            # pregunta por que no puede llenarlo.
            await conn.execute(text(
                "INSERT INTO public.gp_esquema_campo (proyecto_id, tipo_id, "
                "campo_id, obligatorio, solo_lectura, visible, orden) "
                "VALUES (NULL, NULL, :c, :ob, false, true, :o)"),
                {"c": campo_id, "ob": obligatorio, "o": orden})

            # Su indice por expresion, si se filtra por el y vive en el jsonb.
            # Los de columna ya tienen los suyos. La clave viene de estas listas
            # y no de fuera, asi que interpolarla es seguro.
            if filtrable and almacenamiento == "JSONB":
                if tipo in ("NUMERO", "DECIMAL"):
                    expresion = f"((campos ->> '{clave}')::numeric)"
                elif tipo in ("FECHA", "FECHA_HORA"):
                    expresion = f"((campos ->> '{clave}')::timestamptz)"
                else:
                    expresion = f"((campos ->> '{clave}'))"
                await conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS "ix_gp_inc_campo_{clave}" '
                    f'ON public.gp_incidencia {expresion}'))

        for orden, fila in enumerate(NATIVOS):
            (clave, nombre, tipo, seccion, ayuda, validacion, filtrable,
             almacenamiento, columna, del_sistema, defecto, obligatorio) = fila
            entidad = TIPOS_DE_ENTIDAD.get(tipo)
            await _sembrar_campo(
                clave, nombre, tipo, seccion, ayuda, validacion, filtrable,
                "ENTIDAD" if entidad else "PROPIO", entidad, almacenamiento,
                columna, del_sistema, defecto, obligatorio, [], orden)

        for orden, fila in enumerate(CONFIGURABLES):
            (clave, nombre, tipo, seccion, ayuda, validacion, filtrable,
             opciones) = fila
            entidad = TIPOS_DE_ENTIDAD.get(tipo)
            await _sembrar_campo(
                clave, nombre, tipo, seccion, ayuda, validacion, filtrable,
                "ENTIDAD" if entidad else "PROPIO", entidad, "JSONB", None,
                False, None, False, opciones, 100 + orden)

        # ── Cómo se relacionan dos incidencias ──
        #
        # Con su nombre en los dos sentidos: el vínculo se guarda una vez —A
        # bloquea a B— y se lee desde los dos lados, así que hay que saber cómo
        # se llama visto desde B.
        for orden, (clave, nombre, inverso) in enumerate((
            ("BLOQUEA", "bloquea a", "bloqueada por"),
            ("DUPLICA", "duplica a", "duplicada por"),
            ("RELACIONA", "se relaciona con", "se relaciona con"),
            ("CAUSA", "causa", "causada por"),
            ("DEPENDE", "depende de", "requerida por"),
        )):
            await conn.execute(text(
                "INSERT INTO public.gp_tipo_vinculo (clave, nombre, inverso, "
                "orden, activo) VALUES (:c, :n, :i, :o, true) "
                "ON CONFLICT (clave) DO NOTHING"),
                {"c": clave, "n": nombre, "i": inverso, "o": orden})

        # ── Un proyecto para empezar ──
        hay = (await conn.execute(
            text("SELECT count(*) FROM public.gp_proyecto"))).scalar() or 0
        if hay == 0:
            await conn.execute(text(
                "INSERT INTO public.gp_proyecto (clave, nombre, descripcion, "
                "icono, color, workflow_id, contador, restringido, "
                "incidencia_automatica, archivado, created_at, updated_at) "
                "SELECT 'SOP', 'Soporte y mantenimiento', "
                "'Lo que llega por el chat de soporte y el trabajo que se deriva.', "
                "'◈', '#2F6FEB', id, 0, false, true, false, now(), now() "
                "FROM public.gp_workflow WHERE por_defecto = true LIMIT 1"))


async def _esquemas_de_clientes() -> list[str]:
    """Los esquemas de los clientes dados de alta.

    Se lee con SQL directo porque corre antes de que el registro exista, la
    primera vez que arranca.
    """
    async with engine.begin() as conn:
        existe = await conn.execute(text(
            "SELECT to_regclass('public.plataforma_cliente')"
        ))
        if existe.scalar() is None:
            return []
        r = await conn.execute(text(
            "SELECT esquema FROM public.plataforma_cliente WHERE activo = true"
        ))
        return [e for (e,) in r.all() if e and e != ESQUEMA_POR_DEFECTO]


async def _migrar_esquema(esquema: str) -> None:
    """Deja un esquema al día con el juego completo de tablas.

    Es la misma migración de siempre, ahora aplicada por cliente: cada uno tiene
    sus propias tablas y hay que ponerlas al día una por una.
    """
    # 0. Checklists: la configuración pasó a la jerarquía clasificación →
    #    sistema → pregunta, con banco global de preguntas. Las tablas de la
    #    versión anterior (secciones e ítems propios de cada plantilla) tienen
    #    otra forma y `create_all` no altera tablas existentes.
    #
    #    Las vacías se eliminan. Las que tengan datos se RENOMBRAN a `_v1` en vez
    #    de borrarse: así no se pierde nada y `create_all` puede construir la
    #    estructura nueva al lado.
    #
    #    Dejarlas en su sitio sería lo peor de los dos mundos: la API esperaría
    #    `pregunta_id` y la tabla tendría `item_id`, así que el módulo quedaría
    #    roto en silencio. Entre perder datos y romper el módulo, la salida es
    #    conservar los datos aparte y dejar el módulo funcionando.
    # WFM: las jornadas nacieron en el WMS (wms_jornadas) y pasaron al módulo
    # de personal. Se renombran antes de `create_all` para conservar los datos
    # (las llaves foráneas siguen a la tabla renombrada).
    async with _conexion(esquema) as conn:
        for viejo, nuevo in (("wms_jornadas", "per_jornadas"), ("wms_jornada_pausas", "per_jornada_pausas")):
            hay_viejo = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": f'"{esquema}".{viejo}'})).scalar()
            hay_nuevo = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": f'"{esquema}".{nuevo}'})).scalar()
            if hay_viejo and not hay_nuevo:
                await conn.execute(text(f"ALTER TABLE {viejo} RENAME TO {nuevo}"))

    async with _conexion(esquema) as conn:
        existe = await conn.execute(text(
            "SELECT to_regclass(:t)"), {"t": f'"{esquema}".eam_chk_item'})
        if existe.scalar():
            usadas = await conn.execute(text("SELECT count(*) FROM eam_chk_ejecucion"))
            tablas = ("eam_chk_foto", "eam_chk_respuesta", "eam_chk_programacion",
                      "eam_chk_ejecucion", "eam_chk_item", "eam_chk_seccion")
            if (usadas.scalar() or 0) == 0:
                for tabla in tablas:
                    await conn.execute(text(f"DROP TABLE IF EXISTS {tabla} CASCADE"))
            else:
                for tabla in tablas:
                    await conn.execute(text(
                        f"ALTER TABLE IF EXISTS {tabla} RENAME TO {tabla}_v1"))
                logging.getLogger("uvicorn.error").warning(
                    "Checklists en «%s»: la estructura anterior tenía inspecciones. "
                    "Sus tablas quedaron como eam_chk_*_v1 para poder consultarlas; "
                    "el módulo arranca con la estructura nueva.", esquema)

    #    `ALTER TABLE ... RENAME TO` NO renombra los índices ni las
    #    restricciones, y esos nombres son únicos por esquema. Si se dejan como
    #    están, crear la tabla nueva falla con «ya existe» y se cae la migración
    #    entera — incluidas las tablas de otros módulos que vengan detrás.
    #
    #    Va fuera del bloque anterior y es idempotente: solo toca índices de
    #    tablas ya renombradas cuyo nombre no lleve todavía el sufijo.
    async with _conexion(esquema) as conn:
        await conn.execute(text(r"""
            DO $$
            DECLARE r record;
            BEGIN
              FOR r IN
                SELECT indexname FROM pg_indexes
                 WHERE schemaname = current_schema()
                   AND tablename LIKE 'eam\_chk\_%\_v1'
                   AND indexname NOT LIKE '%\_v1'
              LOOP
                EXECUTE format('ALTER INDEX %I RENAME TO %I',
                               r.indexname, r.indexname || '_v1');
              END LOOP;

              -- Las llaves foráneas del archivo apuntan a tablas vivas, así que
              -- impedirían borrar una plantilla solo porque una inspección
              -- vieja la menciona. Son tablas de consulta: se les quitan.
              FOR r IN
                SELECT c.conname, t.relname
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                  JOIN pg_namespace n ON n.oid = t.relnamespace
                 WHERE n.nspname = current_schema()
                   AND c.contype = 'f'
                   AND t.relname LIKE 'eam\_chk\_%\_v1'
              LOOP
                EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I',
                               r.relname, r.conname);
              END LOOP;
            END $$;
        """))

    # 0.b Combustible: la tabla guardaba `litros`/`precio_litro` y ahora lleva
    #     `cantidad` + `unidad`, mas precio unitario, IVA, kilometros recorridos
    #     y la meta de km/galon. En Colombia el combustible se compra por
    #     galones: guardar galones en una columna llamada `litros` es una
    #     mentira que alguien paga caro despues.
    #
    #     `create_all` NO altera tablas existentes, asi que las columnas nuevas
    #     hay que agregarlas a mano. Con la tabla vacia se elimina y se deja que
    #     se reconstruya completa; con datos adentro se agregan una por una y se
    #     avisa, porque convertir litros a galones a ciegas puede estar mal si
    #     alguien ya venia guardando galones ahi.
    async with _conexion(esquema) as conn:
        existe = await conn.execute(text("SELECT to_regclass(:t)"),
                                    {"t": f'"{esquema}".eam_registro_combustible'})
        if existe.scalar():
            columnas = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :e AND table_name = 'eam_registro_combustible'"),
                {"e": esquema})
            nombres = {c for (c,) in columnas.all()}
            if "cantidad" not in nombres:
                filas = await conn.execute(text(
                    "SELECT count(*) FROM eam_registro_combustible"))
                if (filas.scalar() or 0) == 0:
                    await conn.execute(text(
                        "DROP TABLE IF EXISTS eam_registro_combustible CASCADE"))
                else:
                    for columna, tipo in (
                        ("cantidad", "DOUBLE PRECISION"),
                        ("unidad", "VARCHAR(10) DEFAULT 'GALON'"),
                        ("precio_unitario", "DOUBLE PRECISION"),
                        ("subtotal", "DOUBLE PRECISION"),
                        ("iva_pct", "DOUBLE PRECISION DEFAULT 0"),
                        ("iva_valor", "DOUBLE PRECISION"),
                        ("km_recorridos", "DOUBLE PRECISION"),
                        ("meta_km_gal", "DOUBLE PRECISION"),
                        ("cumple_meta", "BOOLEAN"),
                        ("desviacion_pct", "DOUBLE PRECISION"),
                        ("factura", "VARCHAR(60)"),
                        ("estacion", "VARCHAR(150)"),
                        ("registrado_por", "VARCHAR(100)"),
                    ):
                        await conn.execute(text(
                            f"ALTER TABLE eam_registro_combustible "
                            f"ADD COLUMN IF NOT EXISTS {columna} {tipo}"))
                    await conn.execute(text(
                        "UPDATE eam_registro_combustible SET cantidad = litros, "
                        "unidad = 'LITRO', precio_unitario = precio_litro "
                        "WHERE cantidad IS NULL"))
                    logging.getLogger("uvicorn.error").warning(
                        "Combustible en «%s»: habia registros. Se pasaron a cantidad/unidad "
                        "asumiendo LITRO, que es lo que decia la columna. Verifique si en "
                        "realidad eran galones.", esquema)

    # 0.c Inventario: la linea de repuesto de una orden ahora dice de que bodega
    #     sale. `create_all` no altera tablas existentes, asi que la columna se
    #     agrega a mano. Vacia significa «la bodega por defecto».
    async with _conexion(esquema) as conn:
        existe = await conn.execute(text("SELECT to_regclass(:t)"),
                                    {"t": f'"{esquema}".eam_ot_material'})
        if existe.scalar():
            await conn.execute(text(
                "ALTER TABLE eam_ot_material ADD COLUMN IF NOT EXISTS bodega_id INTEGER"))

    # 1. Crear tablas nuevas (incluye la tabla 'roles')
    async with _conexion(esquema) as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 1.a Daily Logistics: la línea de recepción registra su novedad (faltante,
    #     sobrante, dañado, no recibido…). La tabla ya existía.
    async with _conexion(esquema) as conn:
        await conn.execute(text(
            "ALTER TABLE wms_recepciones_detalle ADD COLUMN IF NOT EXISTS novedad VARCHAR(30)"))
        # La línea de picking recuerda de dónde se sacó (va al staging de salida).
        await conn.execute(text(
            "ALTER TABLE wms_picking_detalles ADD COLUMN IF NOT EXISTS ubicacion_alistada_id INTEGER"))

    # 1.b GRC: de texto libre a usuarios, catálogos y vínculos (idempotente).
    async with _conexion(esquema) as conn:
        from app.core.grc_migracion import migrar_grc
        await migrar_grc(conn)

    # 1.c WMS: estibas, depositantes, tareas y kárdex completo (idempotente).
    async with _conexion(esquema) as conn:
        from app.core.wms_migracion import migrar_wms
        await migrar_wms(conn)

    # 2. Añadir columna rol_id a usuarios si no existe (safe para BD existentes)
    async with _conexion(esquema) as conn:
        await conn.execute(text(
            "ALTER TABLE usuarios "
            "ADD COLUMN IF NOT EXISTS rol_id INTEGER "
            "REFERENCES roles(id) ON DELETE SET NULL"
        ))
        # Añadir usuario_id a conductores para linkear con login de conductor
        await conn.execute(text(
            "ALTER TABLE conductores "
            "ADD COLUMN IF NOT EXISTS usuario_id INTEGER "
            "REFERENCES usuarios(id) ON DELETE SET NULL"
        ))
        # El tipo de trabajo se mostraba en pantalla con cinco campos que la
        # tabla no tenía: la página los guardaba en memoria y se perdían al
        # recargar. Ahora existen de verdad.
        for columna, tipo in (
            ("duracion", "VARCHAR(40)"),
            ("requiere_taller", "BOOLEAN DEFAULT false"),
            ("requiere_materiales", "BOOLEAN DEFAULT false"),
            ("sistema", "VARCHAR(100)"),
            ("subsistema", "VARCHAR(100)"),
        ):
            await conn.execute(text(
                f"ALTER TABLE eam_tipo_trabajo ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

        # Catálogos nuevos de llantas: zona, motivo de fin de vida y banda de reencauche
        await conn.execute(text(
            "ALTER TABLE eam_neumatico "
            "ADD COLUMN IF NOT EXISTS zona_id INTEGER "
            "REFERENCES eam_zona_neumatico(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_neumatico "
            "ADD COLUMN IF NOT EXISTS motivo_fin_vida_id INTEGER "
            "REFERENCES eam_motivo_fin_vida(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_neumatico ADD COLUMN IF NOT EXISTS dot VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_neumatico ADD COLUMN IF NOT EXISTS tipo_rin VARCHAR(30)"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_reencauche_detalle "
            "ADD COLUMN IF NOT EXISTS banda_id INTEGER "
            "REFERENCES eam_banda_reencauche(id) ON DELETE SET NULL"
        ))
        # Jerarquía de activos que usan llantas: cantidad de repuestos en el activo
        # (ya existía numero_ejes/tiene_repuesto) + trazabilidad de espejo cuando
        # el vehículo se creó originalmente en TMS/Flota y se vinculó al CMMS.
        await conn.execute(text(
            "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS cantidad_repuestos INTEGER DEFAULT 1"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS origen VARCHAR(20) DEFAULT 'EAM'"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS origen_id INTEGER"
        ))
        # Catálogo de tipos de activo (jerarquía: qué tipos usan llantas y por lo
        # tanto aparecen como vehículo seleccionable en el módulo de Neumáticos).
        await conn.execute(text("""
            INSERT INTO eam_tipo_activo (codigo, nombre, usa_llantas, activo, created_at, updated_at)
            VALUES
                ('VEHICULO', 'Vehículo', true, true, now(), now()),
                ('REMOLQUE', 'Remolque', true, true, now(), now()),
                ('MOTOCICLETA', 'Motocicleta', true, true, now(), now()),
                ('MONTACARGAS', 'Montacargas', true, true, now(), now()),
                ('EQUIPO_PATIO', 'Equipo de patio', true, true, now(), now()),
                ('EQUIPO_LOGISTICO', 'Equipo logístico', false, true, now(), now()),
                ('MAQUINARIA', 'Maquinaria', false, true, now(), now()),
                ('INFRAESTRUCTURA', 'Infraestructura', false, true, now(), now()),
                ('BODEGA', 'Bodega', false, true, now(), now()),
                ('EDIFICACION', 'Edificación', false, true, now(), now()),
                ('EQUIPO_TECNOLOGICO', 'Equipo tecnológico', false, true, now(), now()),
                ('EQUIPO_INDUSTRIAL', 'Equipo industrial', false, true, now(), now()),
                ('HERRAMIENTA', 'Herramienta', false, true, now(), now()),
                ('ACTIVO_CRITICO', 'Activo crítico', false, true, now(), now()),
                ('OTRO', 'Otro', false, true, now(), now())
            ON CONFLICT (codigo) DO NOTHING
        """))
        await conn.execute(text(
            "ALTER TABLE eam_neumatico ADD COLUMN IF NOT EXISTS es_usada BOOLEAN DEFAULT false"
        ))
        # Cuánto puede subir una profundidad respecto de la anterior sin que se
        # tome por error. Es la variación normal de un profundímetro; por encima
        # de eso, el labrado no crece y el dato está mal.
        await conn.execute(text(
            "ALTER TABLE eam_neumatico_config "
            "ADD COLUMN IF NOT EXISTS tolerancia_profundidad DOUBLE PRECISION DEFAULT 0.5"
        ))
        # Catálogo jerárquico de llantas/bandas: las marcas, dimensiones y
        # referencias que ya estaban escritas a mano en los registros existentes
        # se suben al catálogo para no perder nada al pasar a listas cerradas.
        await conn.execute(text("""
            INSERT INTO eam_marca_neumatico (nombre, ambito, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(marca), 'LLANTA', true, now(), now()
            FROM eam_neumatico WHERE marca IS NOT NULL AND TRIM(marca) <> ''
            ON CONFLICT (nombre, ambito) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_dimension_neumatico (nombre, ambito, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(medida), 'LLANTA', true, now(), now()
            FROM eam_neumatico WHERE medida IS NOT NULL AND TRIM(medida) <> ''
            ON CONFLICT (nombre, ambito) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_referencia_neumatico (marca_id, nombre, ambito, activo, created_at, updated_at)
            SELECT DISTINCT m.id, TRIM(n.referencia), 'LLANTA', true, now(), now()
            FROM eam_neumatico n
            JOIN eam_marca_neumatico m ON m.nombre = TRIM(n.marca) AND m.ambito = 'LLANTA'
            WHERE n.referencia IS NOT NULL AND TRIM(n.referencia) <> ''
            ON CONFLICT (marca_id, nombre) DO NOTHING
        """))
        # Profundidad inicial por referencia+dimensión, tomada de lo ya registrado
        await conn.execute(text("""
            INSERT INTO eam_referencia_dimension (referencia_id, dimension_id, profundidad_inicial, activo, created_at, updated_at)
            SELECT DISTINCT ON (r.id, d.id) r.id, d.id, n."profundidad_diseño", true, now(), now()
            FROM eam_neumatico n
            JOIN eam_marca_neumatico m ON m.nombre = TRIM(n.marca) AND m.ambito = 'LLANTA'
            JOIN eam_referencia_neumatico r ON r.marca_id = m.id AND r.nombre = TRIM(n.referencia)
            JOIN eam_dimension_neumatico d ON d.nombre = TRIM(n.medida) AND d.ambito = 'LLANTA'
            WHERE n."profundidad_diseño" IS NOT NULL
            ON CONFLICT (referencia_id, dimension_id) DO NOTHING
        """))
        # Mismo criterio para las bandas de reencauche ya registradas
        await conn.execute(text("""
            INSERT INTO eam_marca_neumatico (nombre, ambito, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(marca), 'BANDA', true, now(), now()
            FROM eam_banda_reencauche WHERE marca IS NOT NULL AND TRIM(marca) <> ''
            ON CONFLICT (nombre, ambito) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_dimension_neumatico (nombre, ambito, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(dimension), 'BANDA', true, now(), now()
            FROM eam_banda_reencauche WHERE dimension IS NOT NULL AND TRIM(dimension) <> ''
            ON CONFLICT (nombre, ambito) DO NOTHING
        """))
        # Configuración de llantas por eje (no solo un número global de ejes):
        # cuántas llantas trae cada eje individual, para representar vehículos
        # reales que no siguen el patrón simple "eje1=2, resto=4" (uniformes,
        # combos cabezote+trailer, motos, etc.)
        await conn.execute(text(
            "ALTER TABLE eam_esquema_vehiculo ADD COLUMN IF NOT EXISTS codigo VARCHAR(30)"
        ))
        await conn.execute(text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_eam_esquema_vehiculo_codigo') THEN "
            "ALTER TABLE eam_esquema_vehiculo ADD CONSTRAINT uq_eam_esquema_vehiculo_codigo UNIQUE (codigo); "
            "END IF; END $$;"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_esquema_vehiculo ADD COLUMN IF NOT EXISTS layout JSON"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS layout_llantas JSON"
        ))
        # Catálogo estándar de esquemas de ejes/llantas (referencia de la industria
        # de transporte: uniformes, camiones con eje direccional simple + ejes
        # duales, combos cabezote+trailer, motos, trailers especializados). Los
        # arreglos `layout` son la cantidad de llantas por cada eje, en orden.
        await conn.execute(text(f"""
            INSERT INTO eam_esquema_vehiculo
                (codigo, nombre, numero_ejes, layout, tiene_repuesto, cantidad_repuestos, activo, created_at, updated_at)
            VALUES
{ESQUEMAS_VEHICULO_SEED}
            ON CONFLICT (codigo) DO NOTHING
        """))

        # ── EAM · Catálogo de vehículos (tipo > marca > línea > modelo) ──
        # La ficha técnica del activo se llenaba a mano y terminaba con
        # "Kenworth", "KENWORTH" y "Ken worth" como tres marcas distintas.
        await conn.execute(text(
            "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS linea VARCHAR(100)"
        ))

        # Identificación del vehículo y datos contables. El número de serie
        # genérico se queda para los activos que no son vehículos.
        for columna, tipo in [
            ("numero_motor", "VARCHAR(100)"),
            ("numero_chasis", "VARCHAR(100)"),
            ("numero_carroceria", "VARCHAR(100)"),
            ("observaciones", "TEXT"),
            ("observaciones_adicionales", "TEXT"),
            ("cuenta_contable", "VARCHAR(80)"),
            ("centro_costo", "VARCHAR(120)"),
        ]:
            await conn.execute(text(
                "ALTER TABLE eam_activo ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))

        # Órdenes de trabajo: imputación contable, sede y origen de la OT.
        for columna, tipo in [
            ("centro_costo", "VARCHAR(120)"),
            ("ciudad", "VARCHAR(100)"),
            ("afecta_disponibilidad", "BOOLEAN DEFAULT true"),
            ("es_falla", "BOOLEAN DEFAULT false"),
            ("fecha_posible_cierre", "TIMESTAMP"),
        ]:
            await conn.execute(text(
                "ALTER TABLE eam_orden_trabajo ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))

        # Líneas de la OT. eam_ot_mano_obra pasa a ser el detalle de trabajos,
        # así que el técnico deja de ser obligatorio: una OT se cotiza antes de
        # saber quién la ejecuta.
        for columna, tipo in [
            ("tipo_trabajo_id", "INTEGER"),
            ("sistema", "VARCHAR(100)"),
            ("subsistema", "VARCHAR(100)"),
            ("observaciones", "TEXT"),
        ]:
            await conn.execute(text(
                "ALTER TABLE eam_ot_mano_obra ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))
        await conn.execute(text(
            "ALTER TABLE eam_ot_mano_obra ALTER COLUMN tecnico DROP NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_ot_mano_obra ALTER COLUMN actividad TYPE VARCHAR(300)"
        ))

        # ── MES · productos y movimientos entre módulos ──
        # `familia` es la segunda mitad del código autollenado (`PT-BOLSA-0001`).
        await conn.execute(text(
            "ALTER TABLE mes_producto ADD COLUMN IF NOT EXISTS familia VARCHAR(60)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mes_producto_familia "
            "ON mes_producto (familia)"))
        # El destino de un traslado. Sin esta columna, una TRANSFERENCIA salía
        # del módulo origen y no entraba a ninguna parte: el material
        # desaparecía del saldo de WIP. `mes_devolucion` la crea `create_all`.
        for columna, tipo in [("celda_destino_id", "INTEGER"),
                              ("devolucion_id", "INTEGER")]:
            await conn.execute(text(
                "ALTER TABLE mes_wip ADD COLUMN IF NOT EXISTS %s %s"
                % (columna, tipo)))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_mes_wip_devolucion "
            "ON mes_wip (devolucion_id)"))

        # ── EAM · garantías ──
        # La pantalla mostraba qué cubre la garantía, a quién llamar en el
        # proveedor, qué documento la respalda y quién responde adentro; la
        # tabla no guardaba ninguno de los cuatro. La tabla de reclamaciones
        # la crea `create_all`: es nueva.
        for columna, tipo in [
            ("cobertura", "TEXT"),
            ("contacto_proveedor", "VARCHAR(120)"),
            ("telefono_proveedor", "VARCHAR(40)"),
            ("documento", "VARCHAR(300)"),
            ("responsable", "VARCHAR(120)"),
        ]:
            await conn.execute(text(
                "ALTER TABLE eam_garantia ADD COLUMN IF NOT EXISTS %s %s"
                % (columna, tipo)))

        # ── TMS · motivo del in-full ──
        # La completitud de una entrega la confirma una persona; si no llegó
        # completa, dice qué faltó.
        await conn.execute(text(
            "ALTER TABLE tms_viaje ADD COLUMN IF NOT EXISTS otif_motivo VARCHAR(300)"))

        # ── SST · matriz GTC 45 ──
        # Los tres factores de los que sale el nivel de riesgo. Las tablas de
        # brigada, simulacros, períodos y configuración las crea `create_all`.
        for columna in ("nivel_deficiencia", "nivel_exposicion",
                        "nivel_consecuencia", "expuestos"):
            await conn.execute(text(
                "ALTER TABLE sst_riesgos ADD COLUMN IF NOT EXISTS %s INTEGER" % columna))

        # ── MES · terminal de planta ──
        # Un usuario de la plataforma por operario, y su PIN de terminal. Sin
        # esto la terminal se identifica con un código que cualquiera puede
        # escribir: el registro diría quién DIJO que era, no quién era, y la
        # productividad por operario dejaría de ser medible.
        for columna, tipo in [("usuario_id", "INTEGER"), ("pin", "VARCHAR(8)")]:
            await conn.execute(text(
                "ALTER TABLE mes_operario ADD COLUMN IF NOT EXISTS %s %s"
                % (columna, tipo)))
        # Un usuario no puede ser dos operarios. Va como índice único parcial
        # porque `usuario_id` es opcional: los operarios que todavía no tienen
        # cuenta conviven con los que sí.
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_mes_operario_usuario "
            "ON mes_operario (usuario_id) WHERE usuario_id IS NOT NULL"))

        # La parada puede colgar de una estación y no solo de una ejecución: una
        # avería se reporta desde la máquina donde ocurre. Sin esto quedaba
        # fuera del registro, y una estación que produjo 200 unidades pero
        # estuvo parada tres horas se veía igual que una que no paró nunca.
        await conn.execute(text(
            "ALTER TABLE mes_parada ALTER COLUMN ejecucion_id DROP NOT NULL"))
        for columna, tipo in [("avance_id", "INTEGER"), ("operario_id", "INTEGER")]:
            await conn.execute(text(
                "ALTER TABLE mes_parada ADD COLUMN IF NOT EXISTS %s %s"
                % (columna, tipo)))
        # Alcance de la rutina por jerarquía: tipo → marca → línea. Así una
        # rutina se escribe una vez y cubre a todos los activos que encajan.
        for columna, tipo in [("marca", "VARCHAR(100)"), ("linea", "VARCHAR(100)")]:
            await conn.execute(text(
                "ALTER TABLE eam_plan_mantenimiento ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))
        # El trabajo de la rutina se queda con la mano de obra; los materiales
        # se mudaron a eam_plan_repuesto, para que la rutina se arme igual que
        # la OT que va a generar.
        await conn.execute(text(
            "ALTER TABLE eam_plan_detalle ADD COLUMN IF NOT EXISTS orden INTEGER DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE eam_plan_detalle ADD COLUMN IF NOT EXISTS costo_mano_obra DOUBLE PRECISION DEFAULT 0"
        ))
        for columna in ("repuesto_id", "cantidad_repuesto"):
            await conn.execute(text(
                "ALTER TABLE eam_plan_detalle DROP COLUMN IF EXISTS %s" % columna
            ))

        # Las llaves de estas tablas se crearon sin regla de borrado, y sin ella
        # el motor rechaza dos operaciones que la aplicación sí ofrece: borrar
        # una OT que cerró una rutina, y borrar un plan con tareas.
        # create_all no toca constraints existentes, así que se rehacen acá.
        await conn.execute(text("""
            ALTER TABLE eam_plan_activo
            DROP CONSTRAINT IF EXISTS fk_eam_plan_activo_ultima_ot_id_eam_orden_trabajo
        """))
        await conn.execute(text("""
            ALTER TABLE eam_plan_activo
            ADD CONSTRAINT fk_eam_plan_activo_ultima_ot_id_eam_orden_trabajo
            FOREIGN KEY (ultima_ot_id) REFERENCES eam_orden_trabajo(id) ON DELETE SET NULL
        """))
        await conn.execute(text("""
            ALTER TABLE eam_plan_detalle
            DROP CONSTRAINT IF EXISTS fk_eam_plan_detalle_plan_id_eam_plan_mantenimiento
        """))
        await conn.execute(text("""
            ALTER TABLE eam_plan_detalle
            ADD CONSTRAINT fk_eam_plan_detalle_plan_id_eam_plan_mantenimiento
            FOREIGN KEY (plan_id) REFERENCES eam_plan_mantenimiento(id) ON DELETE CASCADE
        """))
        # El cumplimiento pasó a eam_plan_activo: cada activo cubierto vence por
        # su cuenta, así que guardarlo en el plan dejó de tener sentido.
        for columna in (
            "ultima_ejecucion_fecha", "ultima_ejecucion_odometro",
            "ultima_ejecucion_horometro", "ultima_ot_id",
            "proxima_fecha", "proximo_odometro", "proximo_horometro",
        ):
            await conn.execute(text(
                "ALTER TABLE eam_plan_mantenimiento DROP COLUMN IF EXISTS %s" % columna
            ))

        # Montaje de llantas en equipos sin odómetro: se mide por horas.
        await conn.execute(text(
            "ALTER TABLE eam_movimiento_neumatico ADD COLUMN IF NOT EXISTS horometro DOUBLE PRECISION"
        ))

        # Proveedor por línea: cada trabajo o repuesto puede correr por cuenta
        # de un contratista distinto al principal de la OT. NULL = taller interno.
        for tabla in ("eam_ot_mano_obra", "eam_ot_material"):
            await conn.execute(text(
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS contratista_id INTEGER" % tabla
            ))

        # Políticas de GRC: la ficha muestra de qué trata la política y cada
        # cuánto se revisa, pero la tabla solo tenía el alcance.
        for columna, tipo in [
            ("descripcion", "TEXT"),
            ("periodicidad_revision", "VARCHAR(50)"),
        ]:
            await conn.execute(text(
                "ALTER TABLE grc_politica ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))

        # APS: lo que el motor de planeación necesita y las tablas no traían
        # (existencias, peso para consolidar camiones, planta que surte a
        # cada centro de distribución).
        for tabla, columna, tipo in [
            ("aps_parametro", "stock_actual", "DOUBLE PRECISION DEFAULT 0 NOT NULL"),
            ("aps_producto", "peso_kg", "DOUBLE PRECISION"),
            ("aps_ubicacion", "abastecida_por_id", "INTEGER"),
            ("aps_restriccion", "ambito", "VARCHAR(30) DEFAULT 'OTRA' NOT NULL"),
            ("eam_activo", "horas_programadas_mes", "DOUBLE PRECISION"),
            ("ags_cita", "iva_incluido", "DOUBLE PRECISION DEFAULT 0"),
            # POS: lo que el inventario y la factura necesitan para vender.
            ("wms_productos", "codigo_barras", "VARCHAR(60)"),
            ("wms_productos", "tarifa_iva", "NUMERIC(5,2) DEFAULT 19 NOT NULL"),
            ("wms_productos", "costo_promedio", "NUMERIC(18,4) DEFAULT 0 NOT NULL"),
            ("wms_zonas", "vendible_pos", "BOOLEAN DEFAULT false NOT NULL"),
            ("wms_movimientos_inventario", "costo_unitario", "NUMERIC(18,4)"),
            ("erp_facturas_cliente", "resolucion_id", "INTEGER REFERENCES erp_resolucion_facturacion(id)"),
            ("erp_facturas_cliente", "origen", "VARCHAR(20)"),
            ("erp_facturas_cliente", "estado_dian", "VARCHAR(20)"),
        ]:
            await conn.execute(text(
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s" % (tabla, columna, tipo)
            ))

        # Catálogos organizativos y contables. Se siembran las sedes y áreas
        # típicas y se rescata lo que ya esté escrito a mano en los activos.
        await conn.execute(text("""
            INSERT INTO eam_catalogo_activo (tipo, nombre, activo, created_at, updated_at)
            VALUES
                ('AREA', 'Operaciones',   true, now(), now()),
                ('AREA', 'Mantenimiento', true, now(), now()),
                ('AREA', 'Logística',     true, now(), now()),
                ('AREA', 'Administración',true, now(), now()),
                ('AREA', 'Transporte',    true, now(), now()),
                ('CENTRO_COSTO', 'CC-100 Operaciones',   true, now(), now()),
                ('CENTRO_COSTO', 'CC-200 Mantenimiento', true, now(), now()),
                ('CENTRO_COSTO', 'CC-300 Transporte',    true, now(), now()),
                ('CUENTA_CONTABLE', '1540 Flota y equipo de transporte', true, now(), now()),
                ('CUENTA_CONTABLE', '1520 Maquinaria y equipo',          true, now(), now()),
                ('CUENTA_CONTABLE', '1592 Depreciación acumulada',       true, now(), now())
            ON CONFLICT (tipo, nombre) DO NOTHING
        """))
        for campo, tipo_cat in [("sede", "SEDE"), ("area", "AREA"),
                                ("ubicacion", "UBICACION"), ("responsable", "RESPONSABLE")]:
            await conn.execute(text("""
                INSERT INTO eam_catalogo_activo (tipo, nombre, activo, created_at, updated_at)
                SELECT DISTINCT :tipo, TRIM(%s), true, now(), now()
                FROM eam_activo
                WHERE %s IS NOT NULL AND TRIM(%s) <> ''
                ON CONFLICT (tipo, nombre) DO NOTHING
            """ % (campo, campo, campo)), {"tipo": tipo_cat})

        # Combustibles y motores de arranque
        await conn.execute(text("""
            INSERT INTO eam_tipo_combustible (nombre, activo, created_at, updated_at)
            VALUES ('Diésel', true, now(), now()), ('Gasolina', true, now(), now()),
                   ('GNV', true, now(), now()), ('Eléctrico', true, now(), now()),
                   ('Híbrido', true, now(), now()), ('GLP', true, now(), now())
            ON CONFLICT (nombre) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_motor_activo (nombre, marca, cilindraje_cc, potencia_hp, activo, created_at, updated_at)
            VALUES
                ('Cummins ISX15',   'Cummins', 14900, 500, true, now(), now()),
                ('Cummins ISL9',    'Cummins',  8900, 380, true, now(), now()),
                ('Paccar MX-13',    'Paccar',  12900, 510, true, now(), now()),
                ('Detroit DD15',    'Detroit', 14800, 505, true, now(), now()),
                ('Mercedes OM 457', 'Mercedes',11970, 428, true, now(), now()),
                ('Hino J08E',       'Hino',     7684, 260, true, now(), now()),
                ('Isuzu 4HK1',      'Isuzu',    5193, 190, true, now(), now())
            ON CONFLICT (nombre) DO NOTHING
        """))

        # Marcas por tipo de activo. La marca con tipo NULL sirve para cualquiera.
        await conn.execute(text("""
            INSERT INTO eam_marca_activo (nombre, tipo_activo, activo, created_at, updated_at)
            VALUES
                ('Kenworth',      'VEHICULO', true, now(), now()),
                ('Freightliner',  'VEHICULO', true, now(), now()),
                ('International', 'VEHICULO', true, now(), now()),
                ('Volvo',         'VEHICULO', true, now(), now()),
                ('Scania',        'VEHICULO', true, now(), now()),
                ('Mercedes-Benz', 'VEHICULO', true, now(), now()),
                ('Hino',          'VEHICULO', true, now(), now()),
                ('Chevrolet',     'VEHICULO', true, now(), now()),
                ('Isuzu',         'VEHICULO', true, now(), now()),
                ('JAC',           'VEHICULO', true, now(), now()),
                ('Foton',         'VEHICULO', true, now(), now()),
                ('Toyota',        'VEHICULO', true, now(), now()),
                ('Hyster',        'MONTACARGAS', true, now(), now()),
                ('Yale',          'MONTACARGAS', true, now(), now()),
                ('Toyota',        'MONTACARGAS', true, now(), now()),
                ('Crown',         'MONTACARGAS', true, now(), now()),
                ('Linde',         'MONTACARGAS', true, now(), now()),
                ('Randon',        'REMOLQUE', true, now(), now()),
                ('Fruehauf',      'REMOLQUE', true, now(), now()),
                ('Bawer',         'REMOLQUE', true, now(), now())
            ON CONFLICT (nombre, tipo_activo) DO NOTHING
        """))

        # Líneas de cada marca
        await conn.execute(text("""
            INSERT INTO eam_linea_activo (marca_id, nombre, activo, created_at, updated_at)
            SELECT m.id, v.linea, true, now(), now()
            FROM (VALUES
                ('Kenworth','VEHICULO','T880'), ('Kenworth','VEHICULO','T680'),
                ('Kenworth','VEHICULO','T800'), ('Kenworth','VEHICULO','W900'),
                ('Freightliner','VEHICULO','Cascadia'), ('Freightliner','VEHICULO','M2 106'),
                ('Freightliner','VEHICULO','Columbia'),
                ('International','VEHICULO','LT'), ('International','VEHICULO','ProStar'),
                ('International','VEHICULO','WorkStar'),
                ('Volvo','VEHICULO','FH'), ('Volvo','VEHICULO','FM'), ('Volvo','VEHICULO','VNL'),
                ('Scania','VEHICULO','R 450'), ('Scania','VEHICULO','G 410'),
                ('Mercedes-Benz','VEHICULO','Actros'), ('Mercedes-Benz','VEHICULO','Atego'),
                ('Mercedes-Benz','VEHICULO','Sprinter'),
                ('Hino','VEHICULO','300'), ('Hino','VEHICULO','500'),
                ('Chevrolet','VEHICULO','NPR'), ('Chevrolet','VEHICULO','NHR'),
                ('Isuzu','VEHICULO','NQR'), ('Isuzu','VEHICULO','FTR'),
                ('JAC','VEHICULO','1040'), ('Foton','VEHICULO','Aumark'),
                ('Toyota','VEHICULO','Hilux'), ('Toyota','VEHICULO','Land Cruiser'),
                ('Hyster','MONTACARGAS','H50FT'), ('Hyster','MONTACARGAS','H2.5FT'),
                ('Yale','MONTACARGAS','GLP050'), ('Toyota','MONTACARGAS','8FGCU25'),
                ('Crown','MONTACARGAS','FC 4500'), ('Linde','MONTACARGAS','H25'),
                ('Randon','REMOLQUE','Planchón'), ('Randon','REMOLQUE','Furgón'),
                ('Fruehauf','REMOLQUE','Tanque'), ('Bawer','REMOLQUE','Portacontenedor')
            ) AS v(marca, tipo, linea)
            JOIN eam_marca_activo m ON m.nombre = v.marca AND m.tipo_activo = v.tipo
            ON CONFLICT (marca_id, nombre) DO NOTHING
        """))

        # Rescate de lo ya escrito a mano: las marcas y modelos que hoy tienen
        # los activos entran al catálogo para que nada quede fuera de la lista.
        await conn.execute(text("""
            INSERT INTO eam_marca_activo (nombre, tipo_activo, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(a.marca), a.tipo_activo, true, now(), now()
            FROM eam_activo a
            WHERE a.marca IS NOT NULL AND TRIM(a.marca) <> ''
            ON CONFLICT (nombre, tipo_activo) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_linea_activo (marca_id, nombre, activo, created_at, updated_at)
            SELECT DISTINCT m.id, TRIM(a.modelo), true, now(), now()
            FROM eam_activo a
            JOIN eam_marca_activo m
              ON m.nombre = TRIM(a.marca)
             AND (m.tipo_activo = a.tipo_activo OR (m.tipo_activo IS NULL AND a.tipo_activo IS NULL))
            WHERE a.modelo IS NOT NULL AND TRIM(a.modelo) <> ''
            ON CONFLICT (marca_id, nombre) DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO eam_tipo_combustible (nombre, activo, created_at, updated_at)
            SELECT DISTINCT TRIM(tipo_combustible), true, now(), now()
            FROM eam_activo
            WHERE tipo_combustible IS NOT NULL AND TRIM(tipo_combustible) <> ''
            ON CONFLICT (nombre) DO NOTHING
        """))

        # ── AGS · Agenda de Servicios ────────────────────────────────────
        # Configuración del negocio: una sola fila, con la jornada típica de
        # un local de servicios en Colombia (lunes a sábado, 8am–7pm).
        await conn.execute(text("""
            INSERT INTO ags_config
                (id, nombre_negocio, tipo_negocio, hora_apertura, hora_cierre,
                 dias_laborales, intervalo_agenda_min, moneda, iva_pct,
                 comision_defecto_pct, permite_sobrecupo, anticipacion_minima_min,
                 tolerancia_no_show_min, mensaje_recordatorio, created_at, updated_at)
            VALUES
                (1, 'Mi negocio', 'SALON_BELLEZA', '08:00', '19:00',
                 '[1,2,3,4,5,6]'::json, 30, 'COP', 0,
                 0, false, 0,
                 15,
                 'Hola {cliente}, le recordamos su cita en {negocio} el {fecha} '
                 'a las {hora} para {servicio}. Cualquier cambio nos avisa.',
                 now(), now())
            ON CONFLICT (id) DO NOTHING
        """))

        # Reserva online: columnas añadidas después del módulo inicial. Se
        # entrega apagada (reserva_online_activa=false) para que el negocio
        # decida cuándo abrir su agenda al público.
        for columna, tipo in [
            ("reserva_online_activa", "BOOLEAN DEFAULT false"),
            ("slug", "VARCHAR(80)"),
            ("mensaje_bienvenida", "TEXT"),
            ("dias_max_anticipacion", "INTEGER DEFAULT 30"),
            ("max_citas_pendientes_cliente", "INTEGER DEFAULT 3"),
            ("permite_cancelar_online", "BOOLEAN DEFAULT true"),
            ("horas_min_cancelacion", "INTEGER DEFAULT 4"),
            ("requiere_confirmacion_online", "BOOLEAN DEFAULT true"),
        ]:
            await conn.execute(text(
                "ALTER TABLE ags_config ADD COLUMN IF NOT EXISTS %s %s" % (columna, tipo)
            ))
        await conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_ags_config_slug'
                ) THEN
                    ALTER TABLE ags_config ADD CONSTRAINT uq_ags_config_slug UNIQUE (slug);
                END IF;
            END $$;
        """))
        # Slug inicial para que el enlace público exista desde el primer día
        await conn.execute(text("""
            UPDATE ags_config SET slug = 'mi-negocio'
            WHERE slug IS NULL OR TRIM(slug) = ''
        """))

        # Categorías de arranque que cubren los oficios más comunes del
        # segmento: belleza y barbería (cita corta en local) junto a plomería
        # y albañilería (visita a domicilio que además cobra materiales).
        await conn.execute(text("""
            INSERT INTO ags_categoria_servicio (nombre, descripcion, color, orden, activo, created_at, updated_at)
            VALUES
                ('Peluquería',   'Corte, peinado, cepillado y tratamientos de cabello', '#A21CAF', 1, true, now(), now()),
                ('Barbería',     'Corte masculino, barba y perfilado',                  '#7E22CE', 2, true, now(), now()),
                ('Color y químicos', 'Tinte, mechas, alisado y keratina',               '#C026D3', 3, true, now(), now()),
                ('Manos y pies', 'Manicure, pedicure y uñas',                           '#DB2777', 4, true, now(), now()),
                ('Estética',     'Depilación, limpieza facial y masajes',               '#9333EA', 5, true, now(), now()),
                ('Plomería',     'Instalaciones y reparaciones hidráulicas',            '#0891B2', 6, true, now(), now()),
                ('Albañilería',  'Obra gris, enchape y remodelación',                   '#B45309', 7, true, now(), now()),
                ('Electricidad', 'Instalaciones y reparaciones eléctricas',             '#CA8A04', 8, true, now(), now()),
                ('Otros',        'Servicios varios',                                    '#64748B', 9, true, now(), now())
            ON CONFLICT (nombre) DO NOTHING
        """))

        # Servicios de ejemplo con precio y duración de referencia. La duración
        # es lo que permite a la agenda calcular la hora de fin y detectar
        # cruces; los oficios a domicilio quedan marcados para que pidan
        # dirección y puedan cobrar materiales aparte de la mano de obra.
        await conn.execute(text("""
            INSERT INTO ags_servicio
                (codigo, nombre, categoria_id, duracion_min, precio, costo_insumos,
                 permite_domicilio, cobra_materiales, requiere_anticipo, activo,
                 created_at, updated_at)
            SELECT v.codigo, v.nombre, c.id, v.duracion, v.precio, v.costo,
                   v.domicilio, v.materiales, v.anticipo, true, now(), now()
            FROM (VALUES
                ('SRV-0001', 'Corte de cabello dama',      'Peluquería',       45,  35000,  2000, false, false, false),
                ('SRV-0002', 'Cepillado / peinado',        'Peluquería',       40,  30000,  3000, false, false, false),
                ('SRV-0003', 'Corte de cabello caballero', 'Barbería',         30,  20000,  1000, false, false, false),
                ('SRV-0004', 'Corte + barba',              'Barbería',         45,  30000,  2000, false, false, false),
                ('SRV-0005', 'Perfilado de barba',         'Barbería',         20,  15000,  1000, false, false, false),
                ('SRV-0006', 'Tinte raíz',                 'Color y químicos', 90,  85000, 25000, false, false, false),
                ('SRV-0007', 'Mechas / balayage',          'Color y químicos',180, 220000, 60000, false, false, false),
                ('SRV-0008', 'Keratina',                   'Color y químicos',120, 150000, 45000, false, false, false),
                ('SRV-0009', 'Manicure',                   'Manos y pies',     45,  25000,  4000, false, false, false),
                ('SRV-0010', 'Pedicure',                   'Manos y pies',     60,  35000,  6000, false, false, false),
                ('SRV-0011', 'Uñas acrílicas',             'Manos y pies',    120,  90000, 25000, false, false, false),
                ('SRV-0012', 'Depilación cera',            'Estética',         40,  40000,  8000, false, false, false),
                ('SRV-0013', 'Limpieza facial',            'Estética',         60,  70000, 15000, false, false, false),
                ('SRV-0014', 'Masaje relajante',           'Estética',         60,  80000,  8000, false, false, false),
                ('SRV-0015', 'Visita diagnóstico',         'Plomería',         30,  40000,     0, true,  false, false),
                ('SRV-0016', 'Destape de tubería',         'Plomería',         90, 120000,     0, true,  true,  false),
                ('SRV-0017', 'Cambio de grifería',         'Plomería',         60,  90000,     0, true,  true,  false),
                ('SRV-0018', 'Reparación de fuga',         'Plomería',        120, 150000,     0, true,  true,  false),
                ('SRV-0019', 'Enchape m2',                 'Albañilería',     240,  60000,     0, true,  true,  true),
                ('SRV-0020', 'Resane y pintura',           'Albañilería',     300, 180000,     0, true,  true,  true),
                ('SRV-0021', 'Instalación de tomacorriente','Electricidad',    60,  70000,     0, true,  true,  false),
                ('SRV-0022', 'Revisión eléctrica general', 'Electricidad',     90, 110000,     0, true,  false, false)
            ) AS v(codigo, nombre, categoria, duracion, precio, costo, domicilio, materiales, anticipo)
            LEFT JOIN ags_categoria_servicio c ON c.nombre = v.categoria
            ON CONFLICT (codigo) DO NOTHING
        """))

        # ── Catálogo maestro de la plataforma ────────────────────────────
        # En PostgreSQL una restricción UNIQUE trata los NULL como distintos, así
        # que uq(modulo,tipo,nombre,padre_id) NO protege los catálogos planos:
        # sin esto cada reinicio volvía a insertar todos sus valores. El índice
        # parcial cubre justamente el caso padre_id IS NULL.
        await conn.execute(text("""
            DELETE FROM catalogo_maestro c
            USING catalogo_maestro d
            WHERE c.padre_id IS NULL AND d.padre_id IS NULL
              AND c.modulo = d.modulo AND c.tipo = d.tipo AND c.nombre = d.nombre
              AND c.id > d.id
        """))
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_catalogo_maestro_raiz
            ON catalogo_maestro (modulo, tipo, nombre)
            WHERE padre_id IS NULL
        """))

        # Valores de arranque de los catálogos compartidos y de los módulos que
        # más los necesitan. El resto de catálogos quedan declarados en el
        # registro y vacíos, listos para que cada área los llene.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, codigo, padre_id, orden, activo, created_at, updated_at)
            SELECT 'GLOBAL', v.tipo, v.nombre, v.codigo, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('PAIS', 'Colombia', 'CO', 1),
                ('UNIDAD_MEDIDA', 'Unidad', 'UND', 1),
                ('UNIDAD_MEDIDA', 'Caja', 'CJA', 2),
                ('UNIDAD_MEDIDA', 'Estiba', 'EST', 3),
                ('UNIDAD_MEDIDA', 'Kilogramo', 'KG', 4),
                ('UNIDAD_MEDIDA', 'Tonelada', 'TON', 5),
                ('UNIDAD_MEDIDA', 'Litro', 'LT', 6),
                ('UNIDAD_MEDIDA', 'Galón', 'GAL', 7),
                ('UNIDAD_MEDIDA', 'Metro', 'MT', 8),
                ('UNIDAD_MEDIDA', 'Metro cúbico', 'M3', 9),
                ('MONEDA', 'Peso colombiano', 'COP', 1),
                ('MONEDA', 'Dólar estadounidense', 'USD', 2),
                ('MONEDA', 'Euro', 'EUR', 3),
                ('CENTRO_COSTO', 'CC-100 Operaciones', 'CC-100', 1),
                ('CENTRO_COSTO', 'CC-200 Mantenimiento', 'CC-200', 2),
                ('CENTRO_COSTO', 'CC-300 Transporte', 'CC-300', 3),
                ('CENTRO_COSTO', 'CC-400 Administración', 'CC-400', 4),
                ('CUENTA_CONTABLE', 'Flota y equipo de transporte', '1540', 1),
                ('CUENTA_CONTABLE', 'Maquinaria y equipo', '1520', 2),
                ('CUENTA_CONTABLE', 'Equipo de cómputo', '1528', 3),
                ('CUENTA_CONTABLE', 'Depreciación acumulada', '1592', 4)
            ) AS v(tipo, nombre, codigo, orden)
            ON CONFLICT DO NOTHING
        """))

        # Departamentos de Colombia, colgados del país
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, codigo, padre_id, orden, activo, created_at, updated_at)
            SELECT 'GLOBAL', 'DEPARTAMENTO', v.nombre, v.codigo, p.id, 0, true, now(), now()
            FROM (VALUES
                ('Antioquia','05'), ('Atlántico','08'), ('Bogotá D.C.','11'),
                ('Bolívar','13'), ('Boyacá','15'), ('Caldas','17'), ('Caquetá','18'),
                ('Cauca','19'), ('Cesar','20'), ('Córdoba','23'), ('Cundinamarca','25'),
                ('Chocó','27'), ('Huila','41'), ('La Guajira','44'), ('Magdalena','47'),
                ('Meta','50'), ('Nariño','52'), ('Norte de Santander','54'),
                ('Quindío','63'), ('Risaralda','66'), ('Santander','68'), ('Sucre','70'),
                ('Tolima','73'), ('Valle del Cauca','76'), ('Arauca','81'),
                ('Casanare','85'), ('Putumayo','86'), ('Amazonas','91'),
                ('Guainía','94'), ('Guaviare','95'), ('Vaupés','97'), ('Vichada','99'),
                ('Archipiélago de San Andrés','88')
            ) AS v(nombre, codigo)
            JOIN catalogo_maestro p
              ON p.modulo = 'GLOBAL' AND p.tipo = 'PAIS' AND p.nombre = 'Colombia'
            ON CONFLICT DO NOTHING
        """))

        # Principales ciudades, colgadas de su departamento
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, codigo, padre_id, orden, activo, created_at, updated_at)
            SELECT 'GLOBAL', 'CIUDAD', v.ciudad, v.codigo, d.id, 0, true, now(), now()
            FROM (VALUES
                ('Medellín','05001','Antioquia'), ('Bello','05088','Antioquia'),
                ('Itagüí','05360','Antioquia'), ('Envigado','05266','Antioquia'),
                ('Rionegro','05615','Antioquia'), ('Apartadó','05045','Antioquia'),
                ('Barranquilla','08001','Atlántico'), ('Soledad','08758','Atlántico'),
                ('Bogotá D.C.','11001','Bogotá D.C.'),
                ('Cartagena','13001','Bolívar'), ('Magangué','13430','Bolívar'),
                ('Tunja','15001','Boyacá'), ('Duitama','15238','Boyacá'), ('Sogamoso','15759','Boyacá'),
                ('Manizales','17001','Caldas'),
                ('Florencia','18001','Caquetá'),
                ('Popayán','19001','Cauca'),
                ('Valledupar','20001','Cesar'),
                ('Montería','23001','Córdoba'),
                ('Soacha','25754','Cundinamarca'), ('Facatativá','25269','Cundinamarca'),
                ('Zipaquirá','25899','Cundinamarca'), ('Chía','25175','Cundinamarca'),
                ('Funza','25286','Cundinamarca'), ('Mosquera','25473','Cundinamarca'),
                ('Madrid','25430','Cundinamarca'), ('Girardot','25307','Cundinamarca'),
                ('Quibdó','27001','Chocó'),
                ('Neiva','41001','Huila'),
                ('Riohacha','44001','La Guajira'),
                ('Santa Marta','47001','Magdalena'),
                ('Villavicencio','50001','Meta'),
                ('Pasto','52001','Nariño'), ('Ipiales','52356','Nariño'),
                ('Cúcuta','54001','Norte de Santander'),
                ('Armenia','63001','Quindío'),
                ('Pereira','66001','Risaralda'), ('Dosquebradas','66170','Risaralda'),
                ('Bucaramanga','68001','Santander'), ('Floridablanca','68276','Santander'),
                ('Girón','68307','Santander'), ('Barrancabermeja','68081','Santander'),
                ('Sincelejo','70001','Sucre'),
                ('Ibagué','73001','Tolima'), ('Espinal','73268','Tolima'),
                ('Cali','76001','Valle del Cauca'), ('Palmira','76520','Valle del Cauca'),
                ('Buenaventura','76109','Valle del Cauca'), ('Tuluá','76834','Valle del Cauca'),
                ('Yumbo','76892','Valle del Cauca'), ('Buga','76111','Valle del Cauca'),
                ('Arauca','81001','Arauca'),
                ('Yopal','85001','Casanare'),
                ('Mocoa','86001','Putumayo'),
                ('Leticia','91001','Amazonas')
            ) AS v(ciudad, codigo, depto)
            JOIN catalogo_maestro d
              ON d.modulo = 'GLOBAL' AND d.tipo = 'DEPARTAMENTO' AND d.nombre = v.depto
            ON CONFLICT DO NOTHING
        """))

        # Catálogos por módulo con valores de uso corriente en Colombia
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, codigo, padre_id, orden, activo, created_at, updated_at)
            SELECT v.modulo, v.tipo, v.nombre, NULL, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('HCM','TIPO_DOCUMENTO','Cédula de ciudadanía',1),
                ('HCM','TIPO_DOCUMENTO','Cédula de extranjería',2),
                ('HCM','TIPO_DOCUMENTO','Pasaporte',3),
                ('HCM','TIPO_DOCUMENTO','Permiso por Protección Temporal',4),
                ('HCM','TIPO_DOCUMENTO','NIT',5),
                ('HCM','TIPO_CONTRATO','Término indefinido',1),
                ('HCM','TIPO_CONTRATO','Término fijo',2),
                ('HCM','TIPO_CONTRATO','Obra o labor',3),
                ('HCM','TIPO_CONTRATO','Aprendizaje SENA',4),
                ('HCM','TIPO_CONTRATO','Prestación de servicios',5),
                ('HCM','TIPO_SALARIO','Ordinario',1),
                ('HCM','TIPO_SALARIO','Integral',2),
                ('HCM','TIPO_SALARIO','Variable por comisión',3),
                ('HCM','MOTIVO_RETIRO','Renuncia voluntaria',1),
                ('HCM','MOTIVO_RETIRO','Terminación de contrato',2),
                ('HCM','MOTIVO_RETIRO','Despido con justa causa',3),
                ('HCM','MOTIVO_RETIRO','Despido sin justa causa',4),
                ('HCM','MOTIVO_RETIRO','Mutuo acuerdo',5),
                ('HCM','MOTIVO_RETIRO','Pensión',6),
                ('HCM','NIVEL_EDUCATIVO','Primaria',1),
                ('HCM','NIVEL_EDUCATIVO','Bachillerato',2),
                ('HCM','NIVEL_EDUCATIVO','Técnico',3),
                ('HCM','NIVEL_EDUCATIVO','Tecnólogo',4),
                ('HCM','NIVEL_EDUCATIVO','Profesional',5),
                ('HCM','NIVEL_EDUCATIVO','Especialización',6),
                ('HCM','NIVEL_EDUCATIVO','Maestría',7),
                ('WMS','TIPO_EMPAQUE','Caja',1),
                ('WMS','TIPO_EMPAQUE','Estiba',2),
                ('WMS','TIPO_EMPAQUE','Saco',3),
                ('WMS','TIPO_EMPAQUE','Granel',4),
                ('WMS','TIPO_EMPAQUE','Canastilla',5),
                ('WMS','MOTIVO_AJUSTE','Conteo físico',1),
                ('WMS','MOTIVO_AJUSTE','Avería',2),
                ('WMS','MOTIVO_AJUSTE','Vencimiento',3),
                ('WMS','MOTIVO_AJUSTE','Faltante',4),
                ('WMS','MOTIVO_AJUSTE','Sobrante',5),
                ('WMS','MOTIVO_DEVOLUCION','Producto averiado',1),
                ('WMS','MOTIVO_DEVOLUCION','Producto vencido',2),
                ('WMS','MOTIVO_DEVOLUCION','Error de despacho',3),
                ('WMS','MOTIVO_DEVOLUCION','Rechazo del cliente',4),
                ('TMS','TIPO_CARGA','Carga seca',1),
                ('TMS','TIPO_CARGA','Refrigerada',2),
                ('TMS','TIPO_CARGA','Congelada',3),
                ('TMS','TIPO_CARGA','Mercancía peligrosa',4),
                ('TMS','TIPO_CARGA','Granel sólido',5),
                ('TMS','TIPO_CARGA','Granel líquido',6),
                ('TMS','TIPO_CARGA','Carga extradimensionada',7),
                ('TMS','TIPO_CARROCERIA','Furgón',1),
                ('TMS','TIPO_CARROCERIA','Planchón',2),
                ('TMS','TIPO_CARROCERIA','Estacas',3),
                ('TMS','TIPO_CARROCERIA','Tanque',4),
                ('TMS','TIPO_CARROCERIA','Portacontenedor',5),
                ('TMS','TIPO_CARROCERIA','Termoking',6),
                ('TMS','TIPO_SERVICIO','Urbano',1),
                ('TMS','TIPO_SERVICIO','Nacional',2),
                ('TMS','TIPO_SERVICIO','Última milla',3),
                ('TMS','TIPO_SERVICIO','Paqueteo',4),
                ('TMS','MOTIVO_DEMORA','Trancón',1),
                ('TMS','MOTIVO_DEMORA','Cargue demorado',2),
                ('TMS','MOTIVO_DEMORA','Descargue demorado',3),
                ('TMS','MOTIVO_DEMORA','Falla mecánica',4),
                ('TMS','MOTIVO_DEMORA','Orden público',5),
                ('TMS','MOTIVO_DEMORA','Clima',6),
                ('SST','TIPO_PELIGRO','Biológico',1),
                ('SST','TIPO_PELIGRO','Físico',2),
                ('SST','TIPO_PELIGRO','Químico',3),
                ('SST','TIPO_PELIGRO','Psicosocial',4),
                ('SST','TIPO_PELIGRO','Biomecánico',5),
                ('SST','TIPO_PELIGRO','Condiciones de seguridad',6),
                ('SST','TIPO_PELIGRO','Fenómenos naturales',7),
                ('SST','PARTE_CUERPO','Cabeza',1),
                ('SST','PARTE_CUERPO','Ojos',2),
                ('SST','PARTE_CUERPO','Manos',3),
                ('SST','PARTE_CUERPO','Brazos',4),
                ('SST','PARTE_CUERPO','Tronco',5),
                ('SST','PARTE_CUERPO','Espalda',6),
                ('SST','PARTE_CUERPO','Piernas',7),
                ('SST','PARTE_CUERPO','Pies',8),
                ('SST','TIPO_EPP','Casco',1),
                ('SST','TIPO_EPP','Gafas de seguridad',2),
                ('SST','TIPO_EPP','Guantes',3),
                ('SST','TIPO_EPP','Botas de seguridad',4),
                ('SST','TIPO_EPP','Protección auditiva',5),
                ('SST','TIPO_EPP','Protección respiratoria',6),
                ('SST','TIPO_EPP','Arnés',7),
                ('QMS','TIPO_NOCONFORMIDAD','Mayor',1),
                ('QMS','TIPO_NOCONFORMIDAD','Menor',2),
                ('QMS','TIPO_NOCONFORMIDAD','Observación',3),
                ('QMS','TIPO_NOCONFORMIDAD','Oportunidad de mejora',4),
                ('QMS','CAUSA_RAIZ','Método',1),
                ('QMS','CAUSA_RAIZ','Mano de obra',2),
                ('QMS','CAUSA_RAIZ','Maquinaria',3),
                ('QMS','CAUSA_RAIZ','Material',4),
                ('QMS','CAUSA_RAIZ','Medición',5),
                ('QMS','CAUSA_RAIZ','Medio ambiente',6),
                ('QMS','TIPO_AUDITORIA','Interna',1),
                ('QMS','TIPO_AUDITORIA','Externa de certificación',2),
                ('QMS','TIPO_AUDITORIA','A proveedor',3),
                ('GRC','CATEGORIA_RIESGO','Estratégico',1),
                ('GRC','CATEGORIA_RIESGO','Operativo',2),
                ('GRC','CATEGORIA_RIESGO','Financiero',3),
                ('GRC','CATEGORIA_RIESGO','Cumplimiento',4),
                ('GRC','CATEGORIA_RIESGO','Tecnológico',5),
                ('GRC','CATEGORIA_RIESGO','Reputacional',6),
                ('GRC','TIPO_POLITICA','Riesgos',1),
                ('GRC','TIPO_POLITICA','Ciberseguridad',2),
                ('GRC','TIPO_POLITICA','Cumplimiento',3),
                ('GRC','TIPO_POLITICA','Continuidad',4),
                ('GRC','TIPO_POLITICA','Terceros y proveedores',5),
                ('GRC','TIPO_POLITICA','Privacidad y datos personales',6),
                ('GRC','TIPO_POLITICA','Ética y conducta',7),
                ('GRC','TIPO_POLITICA','Financiera',8),
                ('GRC','TIPO_POLITICA','Talento humano',9),
                ('GRC','TIPO_POLITICA','Ambiental',10),
                ('LMS','MODALIDAD','Presencial',1),
                ('LMS','MODALIDAD','Virtual',2),
                ('LMS','MODALIDAD','Mixta',3),
                ('DMS','TIPO_SOPORTE','Físico',1),
                ('DMS','TIPO_SOPORTE','Digital',2),
                ('DMS','TIPO_SOPORTE','Híbrido',3),
                ('SCM','TIPO_PROVEEDOR','Bienes',1),
                ('SCM','TIPO_PROVEEDOR','Servicios',2),
                ('SCM','TIPO_PROVEEDOR','Transporte',3),
                ('SCM','TIPO_PROVEEDOR','Contratista',4),
                ('SCM','MOTIVO_RECHAZO','Fuera de presupuesto',1),
                ('SCM','MOTIVO_RECHAZO','Sin justificación',2),
                ('SCM','MOTIVO_RECHAZO','Proveedor no habilitado',3),
                ('ERP','FORMA_PAGO','Contado',1),
                ('ERP','FORMA_PAGO','Crédito 30 días',2),
                ('ERP','FORMA_PAGO','Crédito 60 días',3),
                ('ERP','FORMA_PAGO','Transferencia',4),
                ('ERP','TIPO_IMPUESTO','IVA 19%',1),
                ('ERP','TIPO_IMPUESTO','IVA 5%',2),
                ('ERP','TIPO_IMPUESTO','Excluido',3),
                ('ERP','TIPO_IMPUESTO','Retefuente',4),
                ('ERP','TIPO_IMPUESTO','ReteICA',5),
                ('ERP','TIPO_COMPROBANTE','Factura de venta',1),
                ('ERP','TIPO_COMPROBANTE','Nota crédito',2),
                ('ERP','TIPO_COMPROBANTE','Nota débito',3),
                ('ERP','TIPO_COMPROBANTE','Comprobante de egreso',4),
                ('MES','TURNO','Turno 1 (06:00-14:00)',1),
                ('MES','TURNO','Turno 2 (14:00-22:00)',2),
                ('MES','TURNO','Turno 3 (22:00-06:00)',3),
                ('MES','TIPO_PARADA','Programada',1),
                ('MES','TIPO_PARADA','Falla mecánica',2),
                ('MES','TIPO_PARADA','Falla eléctrica',3),
                ('MES','TIPO_PARADA','Cambio de referencia',4),
                ('MES','TIPO_PARADA','Falta de material',5),
                ('MES','MOTIVO_SCRAP','Defecto de calidad',1),
                ('MES','MOTIVO_SCRAP','Error de operación',2),
                ('MES','MOTIVO_SCRAP','Material fuera de especificación',3),
                ('APS','POLITICA_INVENTARIO','Punto de reorden',1),
                ('APS','POLITICA_INVENTARIO','Min-max',2),
                ('APS','POLITICA_INVENTARIO','Bajo pedido',3),
                ('CRM','ORIGEN_LEAD','Referido',1),
                ('CRM','ORIGEN_LEAD','Página web',2),
                ('CRM','ORIGEN_LEAD','Redes sociales',3),
                ('CRM','ORIGEN_LEAD','Llamada en frío',4),
                ('CRM','ORIGEN_LEAD','Feria o evento',5),
                ('CRM','MOTIVO_PERDIDA','Precio',1),
                ('CRM','MOTIVO_PERDIDA','Tiempo de entrega',2),
                ('CRM','MOTIVO_PERDIDA','Se fue con la competencia',3),
                ('CRM','MOTIVO_PERDIDA','No había presupuesto',4),
                ('CRM','SECTOR_ECONOMICO','Manufactura',1),
                ('CRM','SECTOR_ECONOMICO','Comercio',2),
                ('CRM','SECTOR_ECONOMICO','Alimentos y bebidas',3),
                ('CRM','SECTOR_ECONOMICO','Farmacéutico',4),
                ('CRM','SECTOR_ECONOMICO','Construcción',5),
                ('CRM','SECTOR_ECONOMICO','Agroindustria',6)
            ) AS v(modulo, tipo, nombre, orden)
            ON CONFLICT DO NOTHING
        """))

        # Áreas, cargos y procesos: son los que más aparecen como texto libre en
        # los formularios de GRC, MES, QMS y SST. Sin valores sembrados, cambiarlos
        # a desplegable dejaría una lista vacía, que es peor que el texto libre.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'GLOBAL', v.tipo, v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('AREA','Operaciones',1), ('AREA','Mantenimiento',2),
                ('AREA','Logística',3), ('AREA','Transporte',4),
                ('AREA','Almacén',5), ('AREA','Producción',6),
                ('AREA','Calidad',7), ('AREA','Seguridad y Salud en el Trabajo',8),
                ('AREA','Compras',9), ('AREA','Comercial',10),
                ('AREA','Financiera',11), ('AREA','Gestión Humana',12),
                ('AREA','Tecnología',13), ('AREA','Administración',14),
                ('CARGO','Gerente General',1), ('CARGO','Director de Operaciones',2),
                ('CARGO','Jefe de Operaciones',3), ('CARGO','Jefe de Mantenimiento',4),
                ('CARGO','Jefe de Almacén',5), ('CARGO','Coordinador de Logística',6),
                ('CARGO','Coordinador de Transporte',7), ('CARGO','Supervisor',8),
                ('CARGO','Analista',9), ('CARGO','Auxiliar',10),
                ('CARGO','Técnico de Mantenimiento',11), ('CARGO','Mecánico',12),
                ('CARGO','Conductor',13), ('CARGO','Almacenista',14),
                ('CARGO','Operario',15), ('CARGO','Auxiliar Administrativo',16),
                ('CARGO','Contador',17), ('CARGO','Director Financiero',18),
                ('CARGO','Jefe de Gestión Humana',19), ('CARGO','Coordinador SST',20),
                ('CARGO','Coordinador de Calidad',21),
                ('PROCESO','Gestión Estratégica',1), ('PROCESO','Gestión Comercial',2),
                ('PROCESO','Operaciones Logísticas',3), ('PROCESO','Transporte',4),
                ('PROCESO','Almacenamiento',5), ('PROCESO','Producción',6),
                ('PROCESO','Mantenimiento',7), ('PROCESO','Compras y Abastecimiento',8),
                ('PROCESO','Gestión Humana',9), ('PROCESO','Gestión Financiera',10),
                ('PROCESO','Gestión de Calidad',11), ('PROCESO','Seguridad y Salud',12),
                ('PROCESO','Tecnología de la Información',13),
                ('PROCESO','Servicio al Cliente',14)
            ) AS v(tipo, nombre, orden)
            ON CONFLICT DO NOTHING
        """))

        # TIPO_NOCONFORMIDAD se sembró antes de notar que la clasificación de una
        # NC es un enum de la base. Al salir del registro sus filas quedan
        # huérfanas, así que se limpian.
        await conn.execute(text("""
            DELETE FROM catalogo_maestro
            WHERE modulo = 'QMS' AND tipo = 'TIPO_NOCONFORMIDAD'
        """))

        # Catálogos de QMS que corresponden a columnas de texto libre.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'QMS', v.tipo, v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('TIPO_HALLAZGO','No conformidad',1),
                ('TIPO_HALLAZGO','Observación',2),
                ('TIPO_HALLAZGO','Oportunidad de mejora',3),
                ('TIPO_HALLAZGO','Fortaleza',4),
                ('IMPACTO','Alto',1), ('IMPACTO','Medio',2), ('IMPACTO','Bajo',3),
                ('NORMA_ISO','ISO 9001:2015',1),
                ('NORMA_ISO','ISO 14001:2015',2),
                ('NORMA_ISO','ISO 45001:2018',3),
                ('NORMA_ISO','ISO 28000',4),
                ('NORMA_ISO','BASC',5),
                ('NORMA_ISO','RUC',6),
                ('TIPO_QUEJA','Queja',1), ('TIPO_QUEJA','Reclamo',2),
                ('TIPO_QUEJA','Sugerencia',3), ('TIPO_QUEJA','Felicitación',4),
                ('TIPO_QUEJA','Petición',5),
                ('ESTADO_QUEJA','Abierta',1), ('ESTADO_QUEJA','En gestión',2),
                ('ESTADO_QUEJA','Respondida',3), ('ESTADO_QUEJA','Cerrada',4),
                ('ORIGEN_QUEJA','Correo electrónico',1), ('ORIGEN_QUEJA','Teléfono',2),
                ('ORIGEN_QUEJA','Portal web',3), ('ORIGEN_QUEJA','Presencial',4),
                ('ORIGEN_QUEJA','Redes sociales',5), ('ORIGEN_QUEJA','Encuesta',6),
                ('ORIGEN_QUEJA','Comercial',7),
                ('ESTADO_RIESGO','Activo',1), ('ESTADO_RIESGO','Mitigado',2),
                ('ESTADO_RIESGO','Aceptado',3), ('ESTADO_RIESGO','Transferido',4),
                ('ESTADO_RIESGO','Cerrado',5),
                ('TIPO_CAMBIO','De proceso',1), ('TIPO_CAMBIO','Documental',2),
                ('TIPO_CAMBIO','Tecnológico',3), ('TIPO_CAMBIO','Organizacional',4),
                ('TIPO_CAMBIO','De infraestructura',5),
                ('TIPO_CAMBIO','Normativo',6)
            ) AS v(tipo, nombre, orden)
            ON CONFLICT DO NOTHING
        """))

        # Catálogos de la OT. Estaban vacíos, así que los desplegables del
        # módulo salían sin opciones y no se podía crear una OT completa.
        await conn.execute(text("""
            INSERT INTO eam_tipo_trabajo (nombre, categoria, activo, created_at, updated_at)
            SELECT v.nombre, v.categoria, true, now(), now()
            FROM (VALUES
                ('Mantenimiento preventivo','PREVENTIVO'),
                ('Mantenimiento correctivo','CORRECTIVO'),
                ('Mantenimiento predictivo','PREDICTIVO'),
                ('Inspección visual','INSPECCION'),
                ('Cambio de aceite y filtros','PREVENTIVO'),
                ('Servicio eléctrico','CORRECTIVO'),
                ('Servicio mecánico','CORRECTIVO'),
                ('Servicio hidráulico','CORRECTIVO'),
                ('Calibración','PREDICTIVO'),
                ('Lubricación','PREVENTIVO'),
                ('Soldadura','CORRECTIVO'),
                ('Atención de emergencia','EMERGENCIA')
            ) AS v(nombre, categoria)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_tipo_trabajo t WHERE t.nombre = v.nombre
            )
        """))
        await conn.execute(text("""
            INSERT INTO eam_falla_catalogo (codigo, descripcion, activo, created_at, updated_at)
            SELECT v.codigo, v.descripcion, true, now(), now()
            FROM (VALUES
                ('FAL-01','Falla eléctrica'),
                ('FAL-02','Falla mecánica'),
                ('FAL-03','Fuga de fluidos'),
                ('FAL-04','Desgaste prematuro'),
                ('FAL-05','Sobrecalentamiento'),
                ('FAL-06','Vibración excesiva'),
                ('FAL-07','Ruido anormal'),
                ('FAL-08','Pérdida de presión'),
                ('FAL-09','Corrosión'),
                ('FAL-10','Mantenimiento programado')
            ) AS v(codigo, descripcion)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_falla_catalogo f WHERE f.codigo = v.codigo
            )
        """))
        # Actividades y repuestos: es lo que se ofrece al armar el detalle de
        # una OT, así que sin semilla los desplegables salen vacíos.
        await conn.execute(text("""
            INSERT INTO eam_actividad (nombre, activo, created_at, updated_at)
            SELECT v.nombre, true, now(), now()
            FROM (VALUES
                ('Revisión de frenos'), ('Cambio de filtros'),
                ('Alineación y balanceo'), ('Diagnóstico electrónico'),
                ('Revisión del sistema eléctrico'), ('Cambio de correas'),
                ('Revisión de suspensión'), ('Lavado y engrase'),
                ('Revisión de neumáticos'), ('Cambio de aceite de motor'),
                ('Revisión de batería'), ('Ajuste de frenos'),
                ('Revisión de luces'), ('Revisión de niveles'),
                ('Revisión de embrague'), ('Revisión de dirección'),
                ('Prueba de ruta'), ('Documentación técnica')
            ) AS v(nombre)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_actividad a WHERE a.nombre = v.nombre
            )
        """))
        await conn.execute(text("""
            INSERT INTO eam_repuesto (codigo, nombre, categoria, unidad_medida,
                                      costo_unitario, activo, created_at, updated_at)
            SELECT v.codigo, v.nombre, v.categoria, v.unidad, 0, true, now(), now()
            FROM (VALUES
                ('REP-001','Filtro de aire','Filtros','Unidad'),
                ('REP-002','Filtro de aceite','Filtros','Unidad'),
                ('REP-003','Filtro de combustible','Filtros','Unidad'),
                ('REP-004','Aceite de motor 15W-40','Lubricantes','Galón'),
                ('REP-005','Refrigerante','Lubricantes','Galón'),
                ('REP-006','Pastillas de freno','Frenos','Juego'),
                ('REP-007','Disco de freno','Frenos','Unidad'),
                ('REP-008','Correa de distribución','Motor','Unidad'),
                ('REP-009','Correa del alternador','Motor','Unidad'),
                ('REP-010','Bomba de agua','Motor','Unidad'),
                ('REP-011','Termostato','Motor','Unidad'),
                ('REP-012','Batería','Eléctrico','Unidad'),
                ('REP-013','Bujías','Eléctrico','Juego'),
                ('REP-014','Amortiguador','Suspensión','Unidad'),
                ('REP-015','Kit de embrague','Transmisión','Juego')
            ) AS v(codigo, nombre, categoria, unidad)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_repuesto r WHERE r.codigo = v.codigo
            )
        """))
        await conn.execute(text("""
            INSERT INTO eam_causa_catalogo (descripcion, activo, created_at, updated_at)
            SELECT v.descripcion, true, now(), now()
            FROM (VALUES
                ('Desgaste normal por uso'),
                ('Falta de mantenimiento'),
                ('Error de operación'),
                ('Defecto de fábrica'),
                ('Repuesto de mala calidad'),
                ('Condiciones ambientales'),
                ('Sobrecarga del equipo'),
                ('Fin de vida útil')
            ) AS v(descripcion)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_causa_catalogo c WHERE c.descripcion = v.descripcion
            )
        """))
        await conn.execute(text("""
            INSERT INTO eam_solucion_catalogo (descripcion, activo, created_at, updated_at)
            SELECT v.descripcion, true, now(), now()
            FROM (VALUES
                ('Cambio de pieza'),
                ('Reparación en sitio'),
                ('Reparación en taller'),
                ('Ajuste o calibración'),
                ('Limpieza y lubricación'),
                ('Reemplazo del equipo'),
                ('Actualización de software'),
                ('Sin intervención requerida')
            ) AS v(descripcion)
            WHERE NOT EXISTS (
                SELECT 1 FROM eam_solucion_catalogo s WHERE s.descripcion = v.descripcion
            )
        """))

        # Especialidades del taller interno. Los técnicos cuelgan de ellas y se
        # dan de alta desde CMMS · Configuración · Catálogos; acá solo se
        # siembran las especialidades para que el árbol no arranque vacío.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'ESPECIALIDAD_TECNICO', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Mecánica general', 1), ('Eléctrico y electrónico', 2),
                ('Frenos y suspensión', 3), ('Transmisión y caja', 4),
                ('Hidráulica', 5), ('Llantas y alineación', 6),
                ('Latonería y pintura', 7), ('Refrigeración', 8),
                ('Soldadura', 9), ('Lubricación', 10)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))

        # Contratistas del CMMS: tipo y, colgadas de cada tipo, sus especialidades.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'TIPO_CONTRATISTA', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Taller', 1), ('Proveedor', 2), ('Técnico externo', 3),
                ('Laboratorio', 4), ('Contratista de obra', 5)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'ESPECIALIDAD_CONTRATISTA', v.nombre, t.id, v.orden, true, now(), now()
            FROM (VALUES
                ('Taller','Mecánica automotriz general',1),
                ('Taller','Sistemas eléctricos y electrónicos',2),
                ('Taller','Frenos, suspensión y dirección',3),
                ('Taller','Caja y transmisión',4),
                ('Taller','Latonería y pintura',5),
                ('Taller','Aire acondicionado y refrigeración',6),
                ('Taller','Llantas y alineación',7),
                ('Taller','Reencauche',8),
                ('Proveedor','Repuestos originales',1),
                ('Proveedor','Lubricantes y filtros',2),
                ('Proveedor','Llantas',3),
                ('Proveedor','Motores y garantías',4),
                ('Proveedor','Sistemas hidráulicos',5),
                ('Proveedor','Combustible',6),
                ('Técnico externo','Diagnóstico electrónico y ECU',1),
                ('Técnico externo','Soldadura',2),
                ('Técnico externo','Instrumentación y calibración',3),
                ('Laboratorio','Análisis de aceite',1),
                ('Laboratorio','Ensayos no destructivos',2),
                ('Laboratorio','Metrología',3),
                ('Contratista de obra','Obra civil',1),
                ('Contratista de obra','Instalaciones eléctricas',2),
                ('Contratista de obra','Instalaciones hidrosanitarias',3)
            ) AS v(tipo, nombre, orden)
            JOIN catalogo_maestro t
              ON t.modulo = 'EAM' AND t.tipo = 'TIPO_CONTRATISTA' AND t.nombre = v.tipo
            ON CONFLICT DO NOTHING
        """))

        # Clasificación del análisis de causa raíz. Es lo que el tablero de
        # causas agrupa, así que arranca sembrado: pedirle a quien hace el
        # primer análisis que además invente la taxonomía es la forma segura de
        # terminar con una categoría por analista.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'METODO_DETECCION', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Reporte del operador', 1),
                ('Inspección preoperacional', 2),
                ('Rutina de mantenimiento preventivo', 3),
                ('Análisis de aceite', 4),
                ('Inspección de llantas', 5),
                ('Alarma o telemetría del equipo', 6),
                ('Falla en operación', 7),
                ('Auditoría o inspección de seguridad', 8),
                ('Reporte del taller o contratista', 9)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        # El modo de falla es CÓMO se manifestó, no por qué. Se mantiene
        # genérico a propósito: sirve para un tractocamión y para una planta
        # eléctrica, que es lo que permite compararlos en el mismo tablero.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'MODO_FALLA', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Fuga', 1),
                ('Rotura o fractura', 2),
                ('Desgaste excesivo', 3),
                ('Sobrecalentamiento', 4),
                ('Vibración anormal', 5),
                ('Ruido anormal', 6),
                ('No arranca', 7),
                ('Pérdida de potencia', 8),
                ('Falla eléctrica o de señal', 9),
                ('Obstrucción u obturación', 10),
                ('Corrosión', 11),
                ('Aflojamiento o desajuste', 12),
                ('Contaminación del fluido', 13),
                ('Falla del control o del software', 14)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        # La categoría de causa sigue las 6M, que es la clasificación que casi
        # cualquier analista de mantenimiento reconoce sin que haya que
        # explicarle la lista.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'EAM', 'CATEGORIA_CAUSA', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Falta de mantenimiento', 1),
                ('Mantenimiento mal ejecutado', 2),
                ('Desgaste normal por vida útil', 3),
                ('Error de operación', 4),
                ('Repuesto de mala calidad', 5),
                ('Falla de diseño o especificación', 6),
                ('Sobrecarga del equipo', 7),
                ('Condiciones de la vía o del entorno', 8),
                ('Contaminación o suciedad', 9),
                ('Lubricación inadecuada', 10),
                ('Falta de repuesto o demora logística', 11),
                ('Causa no determinada', 12)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))

        # Los usuarios creados desde la consola quedaron con el nombre del
        # perfil pero sin el vínculo al perfil, y los permisos salen del
        # vínculo: entraban y no veían nada. Se repara emparejando por nombre,
        # que es el dato que sí quedó guardado.
        await conn.execute(text("""
            UPDATE usuarios u SET rol_id = r.id
            FROM roles r
            WHERE u.rol_id IS NULL AND upper(u.rol) = upper(r.nombre)
        """))

        # La operación gana su tipo. `create_all` no altera tablas existentes,
        # así que la columna se agrega a mano en las plantas ya configuradas.
        await conn.execute(text(
            "ALTER TABLE mes_operacion ADD COLUMN IF NOT EXISTS tipo VARCHAR(80)"))

        # ── Catálogos de manufactura ──────────────────────────────────────
        # Arrancan sembrados para que la planta se pueda configurar el primer
        # día. Son listas cortas y genéricas a propósito: sirven igual en una
        # planta de plásticos y en una de alimentos, y quien necesite las suyas
        # las agrega desde la configuración del módulo.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'TIPO_PARADA', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Falla mecánica', 1), ('Falla eléctrica', 2),
                ('Cambio de referencia (setup)', 3), ('Falta de material', 4),
                ('Falta de operario', 5), ('Ajuste de calidad', 6),
                ('Limpieza programada', 7), ('Mantenimiento preventivo', 8),
                ('Corte de energía', 9), ('Sin programa de producción', 10)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'MOTIVO_SCRAP', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Arranque de máquina', 1), ('Fuera de especificación', 2),
                ('Contaminación', 3), ('Daño en el manejo', 4),
                ('Material vencido', 5), ('Error de operación', 6),
                ('Falla de equipo', 7), ('Cambio de referencia', 8)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'FAMILIA_MATERIAL', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Materia prima', 1), ('Insumo de proceso', 2),
                ('Material de empaque', 3), ('Semielaborado', 4),
                ('Producto terminado', 5), ('Repuesto de producción', 6)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'TIPO_EQUIPO', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Mezclador', 1), ('Extrusora', 2), ('Inyectora', 3),
                ('Prensa', 4), ('Troqueladora', 5), ('Horno', 6),
                ('Envasadora', 7), ('Selladora', 8), ('Etiquetadora', 9),
                ('Encajadora', 10), ('Banda transportadora', 11),
                ('Molino', 12), ('Tanque de proceso', 13),
                ('Máquina de corte', 14), ('Robot de manipulación', 15)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'TIPO_OPERACION', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Preparación', 1), ('Dosificación', 2), ('Mezclado', 3),
                ('Transformación', 4), ('Conformado', 5), ('Tratamiento térmico', 6),
                ('Corte', 7), ('Ensamble', 8), ('Llenado', 9),
                ('Sellado', 10), ('Etiquetado', 11), ('Empaque', 12),
                ('Inspección', 13), ('Paletizado', 14)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'TIPO_DEFECTO', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Dimensional', 1), ('Visual o de acabado', 2),
                ('Funcional', 3), ('De empaque o rotulado', 4),
                ('Contaminación', 5), ('Documental', 6)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'DEFECTO', v.nombre, t.id, v.orden, true, now(), now()
            FROM (VALUES
                ('Dimensional','Fuera de tolerancia',1),
                ('Dimensional','Espesor irregular',2),
                ('Visual o de acabado','Rayón superficial',1),
                ('Visual o de acabado','Burbuja o rechupe',2),
                ('Visual o de acabado','Color fuera de patrón',3),
                ('Funcional','No cierra o no ajusta',1),
                ('Funcional','Fuga',2),
                ('De empaque o rotulado','Etiqueta mal ubicada',1),
                ('De empaque o rotulado','Sellado deficiente',2),
                ('Contaminación','Cuerpo extraño',1),
                ('Documental','Lote sin trazabilidad',1)
            ) AS v(tipo, nombre, orden)
            JOIN catalogo_maestro t
              ON t.modulo = 'MES' AND t.tipo = 'TIPO_DEFECTO' AND t.nombre = v.tipo
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'MOTIVO_RETRABAJO', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Defecto recuperable', 1), ('Ajuste de medida', 2),
                ('Reempaque', 3), ('Reetiquetado', 4), ('Reproceso de mezcla', 5)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, padre_id, orden, activo, created_at, updated_at)
            SELECT 'MES', 'CONDICION_ALMACENAMIENTO', v.nombre, NULL, v.orden, true, now(), now()
            FROM (VALUES
                ('Ambiente seco', 1), ('Refrigerado', 2), ('Congelado', 3),
                ('Temperatura controlada', 4), ('Protegido de la luz', 5),
                ('Área de sustancias peligrosas', 6)
            ) AS v(nombre, orden)
            ON CONFLICT DO NOTHING
        """))
        # La lista de líneas de producción del catálogo maestro se retira: las
        # líneas viven en `mes_linea`, con su planta y su capacidad. Solo se
        # borra lo que nadie escribió, para no llevarse por delante algo que
        # alguien hubiera capturado ahí antes de que existiera la tabla.
        await conn.execute(text("""
            DELETE FROM catalogo_maestro
            WHERE modulo = 'MES' AND tipo IN ('LINEA_PRODUCCION', 'TURNO')
              AND NOT EXISTS (SELECT 1 FROM mes_linea)
        """))

        # Los catálogos del CMMS se unificaron en el catálogo maestro: antes
        # `eam_catalogo_activo` tenía su propia lista de áreas, centros de costo
        # y cuentas contables, en paralelo a las compartidas. Se migran los
        # valores para no perder nada y el formulario de activos pasa a leer del
        # maestro. La tabla vieja queda sin uso.
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, codigo, padre_id, orden, activo, created_at, updated_at)
            SELECT 'GLOBAL', e.tipo, TRIM(e.nombre), e.codigo, NULL, 0, e.activo, now(), now()
            FROM eam_catalogo_activo e
            WHERE e.tipo IN ('SEDE','AREA','UBICACION','CENTRO_COSTO','CUENTA_CONTABLE')
              AND TRIM(e.nombre) <> ''
            ON CONFLICT DO NOTHING
        """))

        # La tabla del CMMS escribía la cuenta como "1540 Flota y equipo", con el
        # número dentro del nombre; el maestro separa nombre y código. Al migrar
        # quedaron las dos formas de la misma cuenta, así que se borra la
        # redundante cuando ya existe una con ese código.
        await conn.execute(text("""
            DELETE FROM catalogo_maestro d
            WHERE d.modulo = 'GLOBAL' AND d.tipo = 'CUENTA_CONTABLE'
              AND d.codigo IS NULL
              AND d.nombre ~ '^[0-9]+ '
              AND EXISTS (
                  SELECT 1 FROM catalogo_maestro m
                  WHERE m.modulo = 'GLOBAL' AND m.tipo = 'CUENTA_CONTABLE'
                    AND m.codigo = split_part(d.nombre, ' ', 1)
              )
        """))

    # 3. Sembrar roles y migrar usuarios
    async with AsyncSession(engine) as db:
        async with db.begin():
            await db.execute(text(f'SET search_path TO "{esquema}"'))
            await _seed_roles_and_migrate(db)

    # 4. Configuración de arranque de lubricación.
    #
    # Va en su propia sesión y NO dentro de `db.begin()` porque la siembra hace
    # sus propios commit —necesita los identificadores de los parámetros para
    # poder colgarles los límites—, y una transacción externa abierta se los
    # tragaría. Es idempotente: solo crea lo que falte y nunca pisa lo que la
    # empresa haya ajustado.
    #
    # Un módulo de análisis con los catálogos vacíos no se puede usar: no habría
    # contra qué evaluar la primera muestra.
    async with AsyncSession(engine) as db:
        await db.execute(text(f'SET search_path TO "{esquema}"'))
        try:
            await sembrar_lubricacion(db)
        except Exception as e:   # noqa: BLE001
            # Que falle la siembra no puede impedir que el servidor arranque:
            # es configuración conveniente, no una tabla que alguien necesite
            # para entrar.
            logging.getLogger("uvicorn.error").warning(
                "No se pudo sembrar la configuración de lubricación en «%s»: %s", esquema, e)

    # `create_all` no altera tablas existentes: las columnas que la auditoría
    # financiera necesita se agregan a la tabla que ya estaba.
    async with _conexion(esquema) as conn:
        if (await conn.execute(text(
                "SELECT to_regclass('erp_auditoria')"))).scalar() is not None:
            for columna, tipo in (("empresa_id", "INTEGER"),
                                  ("documento_origen", "VARCHAR(120)")):
                await conn.execute(text(
                    f"ALTER TABLE erp_auditoria "
                    f"ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

        # `contabilizado_en` nació sin zona horaria y en la misma columna
        # convivían dos significados: un endpoint escribía `datetime.now()` y
        # otro `datetime.utcnow()`. Los contenedores corren en UTC, así que los
        # valores guardados YA son UTC y la conversión es exacta —por eso el
        # `AT TIME ZONE 'UTC'`, que declara lo que el dato siempre fue en vez de
        # desplazarlo—. Sin esto, insertar una fecha con zona revienta.
        #
        # Se pregunta por el tipo actual y no se hace a ciegas: sobre una columna
        # YA convertida, `AT TIME ZONE 'UTC'` la devolvería a naive y la
        # reinterpretaría con la zona de la sesión, desplazando las horas en cada
        # arranque. Además reescribe la tabla entera, y esto corre en cada boot
        # de cada worker.
        tipo_actual = (await conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = :e AND table_name = 'erp_comprobantes' "
            "  AND column_name = 'contabilizado_en'"), {"e": esquema})).scalar()
        if tipo_actual == "timestamp without time zone":
            await conn.execute(text(
                "ALTER TABLE erp_comprobantes "
                "ALTER COLUMN contabilizado_en TYPE TIMESTAMPTZ "
                "USING contabilizado_en AT TIME ZONE 'UTC'"))

    # ── Los índices que sostienen la contabilidad ──
    #
    # `create_all` crea los índices declarados en los modelos nuevos, pero
    # `erp_comprobante_lineas` es una tabla vieja y nació sin ninguno: ni por
    # `comprobante_id` ni por `cuenta_id`. TODOS los reportes contables la
    # recorren entera —balance, mayor, diario, estados financieros—, así que con
    # unos pocos miles de asientos cada consulta pasa a leer la tabla completa.
    #
    # Van con `CONCURRENTLY` no: eso exige estar fuera de transacción y acá se
    # está dentro del lock de arranque. Sobre tablas de este tamaño el bloqueo
    # dura milisegundos, y solo la primera vez.
    async with _conexion(esquema) as conn:
        indices = [
            # El JOIN de todos los reportes. Las columnas van INCLUDE para que
            # la suma se resuelva sin volver a la tabla.
            ("ix_ecl_comprobante", "erp_comprobante_lineas",
             "(comprobante_id) INCLUDE (cuenta_id, debito, credito, centro_costo_id)"),
            # El libro mayor filtra por cuenta antes de unir.
            ("ix_ecl_cuenta", "erp_comprobante_lineas", "(cuenta_id)"),
            ("ix_ecl_centro", "erp_comprobante_lineas", "(centro_costo_id)"),
            # El filtro de `_saldos`: empresa, estado y rango de fechas.
            ("ix_ec_empresa_estado_fecha", "erp_comprobantes",
             "(empresa_id, estado, fecha)"),
            ("ix_ec_empresa_periodo", "erp_comprobantes", "(empresa_id, periodo)"),
            # Cartera y su antigüedad.
            ("ix_efc_empresa_estado", "erp_facturas_cliente",
             "(empresa_id, estado, fecha_vencimiento)"),
            ("ix_efp_empresa_estado", "erp_facturas_proveedor",
             "(empresa_id, estado, fecha_vencimiento)"),
            ("ix_epagos_empresa_fecha", "erp_pagos", "(empresa_id, fecha)"),
            # La auditoría se consulta por documento.
            ("ix_eaud_entidad", "erp_auditoria", "(empresa_id, entidad, entidad_id)"),
        ]
        for nombre, tabla, definicion in indices:
            if (await conn.execute(text(
                    "SELECT to_regclass(:t)"), {"t": tabla})).scalar() is None:
                continue
            try:
                await conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} {definicion}"))
            except Exception as e:   # noqa: BLE001
                # Una columna que no exista en un esquema viejo no puede impedir
                # que el servidor arranque; se pierde el índice, no el servicio.
                logging.getLogger("uvicorn.error").warning(
                    "No se pudo crear el índice %s en «%s»: %s", nombre, esquema, e)

        # Los consecutivos dejan de deducirse del máximo de los comprobantes.
        # Para que la numeración siga donde iba, se siembra la tabla con lo que
        # ya está emitido. Sin esto el primer comprobante después de actualizar
        # volvería al 000001 y chocaría contra `uq_comprobante`.
        if (await conn.execute(text(
                "SELECT to_regclass('erp_consecutivos')"))).scalar() is not None:
            await conn.execute(text("""
                INSERT INTO erp_consecutivos (empresa_id, prefijo, anio, ultimo,
                                              created_at, updated_at)
                SELECT empresa_id,
                       split_part(numero, '-', 1)               AS prefijo,
                       split_part(numero, '-', 2)::int          AS anio,
                       max(split_part(numero, '-', 3)::int)     AS ultimo,
                       now(), now()
                FROM erp_comprobantes
                WHERE numero ~ '^[A-Z]+-[0-9]{4}-[0-9]+$'
                GROUP BY 1, 2, 3
                ON CONFLICT (empresa_id, prefijo, anio) DO UPDATE
                    SET ultimo = greatest(erp_consecutivos.ultimo, excluded.ultimo)
            """))

    # ── El núcleo contable ──
    #
    # Sin plan de cuentas ni reglas, la primera factura de una empresa falla con
    # «no hay regla contable para cartera». Sembrarlo es lo que evita que la
    # primera experiencia del módulo financiero sea un error.
    #
    # Es idempotente: sobre una empresa que ya tiene cuentas completa lo que
    # falte y no pisa lo que alguien haya cambiado.
    # Sesión propia sobre el motor, igual que la siembra de lubricación de
    # arriba: `AsyncSessionLocal` no está a la mano en este módulo, y la siembra
    # hace sus propios commit.
    async with AsyncSession(engine) as db:
        await db.execute(text(f'SET search_path TO "{esquema}"'))
        try:
            from app.core import erp_semilla

            await erp_semilla.sembrar_parametros(db)
            empresas = (await db.execute(text(
                "SELECT id FROM erp_empresas WHERE activo = true"))).all()
            for (empresa_id,) in empresas:
                await erp_semilla.sembrar_empresa(db, empresa_id)
            await db.commit()
        except Exception as e:   # noqa: BLE001
            # Igual que arriba: es parametrización conveniente, no algo sin lo
            # cual nadie pueda entrar. Se avisa y se sigue.
            await db.rollback()
            logging.getLogger("uvicorn.error").warning(
                "No se pudo sembrar el núcleo contable en «%s»: %s", esquema, e)


# Número arbitrario pero fijo: identifica este candado y nada más.
_CANDADO_MIGRACION = 918273645


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En producción corren varios procesos y todos arrancan a la vez. Sin
    # candado, los cuatro intentan crear las mismas tablas y chocan con
    # "duplicate key ... pg_type_typname_nsp_index". Con él, el primero migra y
    # los demás esperan y encuentran el trabajo hecho.
    async with engine.begin() as candado:
        await candado.execute(text(f"SELECT pg_advisory_lock({_CANDADO_MIGRACION})"))
        try:
            await _migrar_todo()
        finally:
            await candado.execute(text(f"SELECT pg_advisory_unlock({_CANDADO_MIGRACION})"))

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Canales de venta: trae pedidos, envía estados y publica stock en segundo plano.
    import asyncio
    from app.core.marketplace import trabajador
    tarea_canales = asyncio.create_task(trabajador.ciclo())
    # Tareas de bodega: reabastecimiento de frentes, cola y jornadas olvidadas.
    from app.core import wms_ciclo_tareas
    tarea_bodega = asyncio.create_task(wms_ciclo_tareas.ciclo())
    from app.core import geo
    tarea_geo = asyncio.create_task(geo.ciclo())
    yield
    tarea_canales.cancel()
    tarea_bodega.cancel()
    tarea_geo.cancel()
    await engine.dispose()


async def _sembrar_operador() -> None:
    """Primer arranque de Daily Logistics: la empresa operadora y su administrador.

    En una base recién creada no hay ninguna empresa en el registro, así que
    nadie podría ni iniciar sesión ni entrar a la consola para dar de alta a
    las demás. Se crea la empresa que opera la plataforma —vive en `public`—
    y un administrador dentro de ella. Si ya hay empresas o usuarios, no toca
    nada.
    """
    from app.core.security import hash_password
    from app.infrastructure.models.plataforma import PlataformaCliente, PlataformaModuloCliente

    codigo = os.getenv("DL_OPERADOR_CODIGO", "daily").strip().lower()
    async with AsyncSessionLocal(info={"esquema": ESQUEMA_POR_DEFECTO}) as db:
        hay_clientes = (await db.execute(select(PlataformaCliente.id).limit(1))).first()
        if not hay_clientes:
            cliente = PlataformaCliente(
                codigo=codigo, nombre=os.getenv("DL_OPERADOR_NOMBRE", "Daily Logistics"),
                esquema=ESQUEMA_POR_DEFECTO, activo=True, es_operador=True, color="#4F46E5",
            )
            db.add(cliente)
            await db.flush()
            for clave in ("wms", "pos", "tms"):
                db.add(PlataformaModuloCliente(cliente_id=cliente.id, modulo=clave, activo=True))

        hay_usuarios = (await db.execute(select(Usuario.id).limit(1))).first()
        if not hay_usuarios:
            rol_admin = (await db.execute(
                select(Rol).where(Rol.nombre == "ADMINISTRADOR"))).scalar_one_or_none()
            db.add(Usuario(
                nombre="Administrador", apellido="Daily Logistics",
                email=os.getenv("DL_ADMIN_EMAIL", "admin@dailylogistics.com"),
                username=os.getenv("DL_ADMIN_USUARIO", "admin"),
                hashed_password=hash_password(os.getenv("DL_ADMIN_CLAVE", "Daily@2026")),
                rol="ADMINISTRADOR", rol_id=rol_admin.id if rol_admin else None,
                cargo="Administrador de la plataforma", activo=True,
            ))
        await db.commit()


async def _migrar_todo() -> None:
    # Antes que nada: la tabla particionada del historial de gestión. Tiene que
    # existir antes de que `create_all` pase por ahí, o la crearía sin
    # particiones.
    await _preparar_gestion()
    # El esquema por defecto guarda los datos de quien ya estaba antes de que
    # esto fuera multicliente; ese cliente pasa a ser uno más.
    await _migrar_esquema(ESQUEMA_POR_DEFECTO)
    await _preparar_registro_clientes()
    # Después de `create_all`, que es cuando las tablas del módulo ya existen.
    await _sembrar_gestion()
    # Base nueva: la empresa operadora y su administrador.
    await _sembrar_operador()
    for esquema in await _esquemas_de_clientes():
        await _migrar_esquema(esquema)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Plataforma avanzada de gestión, control y trazabilidad de estibas (pallets)",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ── Lo que la base rechaza se le explica a quien guardó ──────────────────────
# Un código repetido, un texto más largo que la columna o borrar algo que otros
# registros usan llegaban al usuario como «Error interno» (500). El barrido de
# todas las rutas de escritura encontró decenas de formularios así. No es un
# fallo del servidor: es un dato que la base no acepta, y se dice cuál.
from fastapi import Request as _Request  # noqa: E402
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402
from sqlalchemy.exc import DBAPIError as _DBAPIError  # noqa: E402


@app.exception_handler(_DBAPIError)
async def _dato_rechazado(request: _Request, exc: _DBAPIError):
    causa = getattr(getattr(exc, "orig", None), "__cause__", None)
    estado = getattr(causa, "sqlstate", None)
    columna = getattr(causa, "column_name", None)
    detalle = getattr(causa, "detail", None) or ""
    tabla = getattr(causa, "table_name", None)
    if estado == "23505":   # único
        campo = detalle.split("(")[1].split(")")[0] if "(" in detalle else columna
        return _JSONResponse(status_code=409, content={
            "detail": f"Ya existe un registro con ese valor{f' en «{campo}»' if campo else ''}."})
    if estado == "23503":   # llave foránea
        if "is still referenced" in detalle:
            return _JSONResponse(status_code=409, content={
                "detail": "No se puede eliminar: otros registros lo usan"
                          f"{f' ({tabla})' if tabla else ''}. Desactívelo en su lugar."})
        campo = detalle.split("(")[1].split(")")[0] if "(" in detalle else columna
        return _JSONResponse(status_code=422, content={
            "detail": f"La referencia elegida no existe{f' («{campo}»)' if campo else ''}."})
    if estado == "23502":   # obligatorio
        return _JSONResponse(status_code=422, content={
            "detail": f"Falta un dato obligatorio{f': «{columna}»' if columna else ''}."})
    if estado == "22001":   # texto demasiado largo
        return _JSONResponse(status_code=422, content={
            "detail": "Uno de los textos es más largo de lo permitido."})
    if estado in ("22P02", "22007", "22008", "22003"):   # formato, fecha, número fuera de rango
        return _JSONResponse(status_code=422, content={
            "detail": "Uno de los valores no tiene el formato esperado."})
    logging.getLogger(__name__).exception("Error de base de datos no clasificado", exc_info=exc)
    return _JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Resuelve el cliente antes de que la petición toque la base. Se registra
# después de CORS para que las respuestas de error también lleven sus cabeceras.
app.add_middleware(TenantMiddleware)

# Corta el acceso a los módulos que la empresa no tiene contratados. Ocultar el
# módulo en el menú no basta: quien escriba la URL a mano entraría igual.
app.add_middleware(ModulosMiddleware)

# La autenticación se exige a nivel del router: eran 470 rutas sin token, y
# ponerlo en cada firma habría dejado la puerta abierta a que la siguiente
# naciera igual de expuesta. Las excepciones están enumeradas en auth_global.
app.include_router(
    api_router, prefix=settings.API_V1_PREFIX, dependencies=[Depends(exigir_sesion)],
)


@app.get("/health")
# El aviso de versión nueva del frontend (`AvisoDeVersion.tsx`) pregunta aquí,
# bajo /api/v1, porque es lo único que el proxy de la aplicación enruta al
# servidor. Sin esta ruta respondía 404, el aviso ignoraba el error y nunca
# avisaba de una versión publicada.
@app.get("/api/v1/health", include_in_schema=False)
async def health_check():
    return {"status": "ok", "version": settings.VERSION, "service": settings.PROJECT_NAME}
