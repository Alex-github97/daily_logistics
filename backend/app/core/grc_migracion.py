"""
Lleva las tablas GRC de la forma vieja (personas y clasificaciones en texto
libre, enums fijos) a la nueva (usuarios con llave, catálogos configurables,
vínculos reales). Corre en cada arranque, por esquema y después de
`create_all`; es idempotente.

QUÉ PASA CON LOS DATOS QUE YA EXISTEN
- Persona escrita a mano → se vincula al usuario cuyo nombre completo coincide
  (sin mayúsculas ni tildes). Si no coincide con nadie, el dato se ELIMINA: un
  nombre que no es nadie del sistema no se puede asignar ni consultar, y es
  justo lo que había que dejar de tener.
- Clasificación escrita a mano (tipo de comité, marco, sistema crítico…) → si
  coincide con un valor del catálogo se normaliza a su grafía; si no, se
  agrega al catálogo para que quede administrable desde Configuración. Es un
  dato de la empresa, solo le faltaba estar en la base.
- Enum viejo convertido en catálogo (tipo de riesgo, de obligación, de
  auditoría, de tercero) → el nombre legible del catálogo.
- Lo que no tiene una forma coherente se elimina: el conteo suelto de
  participantes del simulacro, el contador de aceptaciones sin nombres, el
  «riesgo asociado» en texto que no corresponde a ningún riesgo, las
  dependencias en texto libre y la tabla de KPI diarios que nadie usaba.
"""
import logging
import unicodedata

from sqlalchemy import text

log = logging.getLogger("uvicorn.error")


# ── Semillas ─────────────────────────────────────────────────────────────────
# (tipo, [(nombre, metadatos-json o None)])
CATALOGOS_GRC = {
    "CATEGORIA_RIESGO": ["Estratégico", "Operativo", "Financiero", "Cumplimiento", "Legal",
                         "Tecnológico", "Ciberseguridad", "Logístico", "Transporte",
                         "Talento humano", "Ambiental", "Reputacional", "Fraude",
                         "Lavado de activos y financiación del terrorismo"],
    "TIPO_COMITE": ["Junta directiva", "Comité de auditoría", "Comité de riesgos",
                    "Comité de ética y cumplimiento", "Comité de seguridad de la información",
                    "Comité de continuidad", "Comité de convivencia laboral", "COPASST"],
    "PERIODICIDAD": ["Mensual", "Bimestral", "Trimestral", "Semestral", "Anual", "Bianual",
                     "Por cambio normativo"],
    "FRECUENCIA_CONTROL": ["Continua", "Por evento", "Diaria", "Semanal", "Mensual",
                           "Trimestral", "Semestral", "Anual"],
    "MARCO_NORMATIVO": ["ISO 31000 — Gestión del riesgo", "ISO 37301 — Sistemas de cumplimiento",
                        "ISO 27001 — Seguridad de la información", "ISO 22301 — Continuidad del negocio",
                        "ISO 9001 — Calidad", "ISO 14001 — Ambiental", "ISO 45001 — Seguridad y salud en el trabajo",
                        "ISO 37001 — Antisoborno", "COSO ERM", "COSO Control interno",
                        "SAGRILAFT (Supersociedades)", "SARLAFT (Superfinanciera)",
                        "Programa de Transparencia y Ética Empresarial (PTEE)",
                        "Ley 1581 de 2012 — Protección de datos personales",
                        "Decreto 1072 de 2015 — SG-SST", "Resolución 0312 de 2019 — Estándares mínimos SST",
                        "Ley 1778 de 2016 — Soborno transnacional", "Código Sustantivo del Trabajo",
                        "Estatuto Tributario", "Normas de transporte (Mintransporte)"],
    "TIPO_POLITICA": ["Riesgos", "Ciberseguridad", "Cumplimiento", "Continuidad",
                      "Terceros y proveedores", "Privacidad y datos personales", "Ética y conducta",
                      "Antisoborno y anticorrupción", "Financiera", "Talento humano", "Ambiental"],
    "TIPO_OBLIGACION": ["Ley", "Decreto", "Resolución", "Circular", "Norma técnica",
                        "Contrato", "Política interna", "Requisito de cliente"],
    "TIPO_AUDITORIA": ["Interna", "Externa", "De certificación", "Financiera", "Operativa",
                       "Tecnológica", "Regulatoria", "De cumplimiento", "A proveedor"],
    "TIPO_HALLAZGO": ["No conformidad mayor", "No conformidad menor", "Observación",
                      "Oportunidad de mejora", "Debilidad de control"],
    "TIPO_INCIDENTE": ["Accidente", "Hurto o pérdida", "Fraude", "Seguridad de la información",
                       "Falla tecnológica", "Incumplimiento normativo", "Ambiental",
                       "Reclamo de cliente", "Daño a la mercancía", "Interrupción de la operación"],
    "TIPO_EVIDENCIA": ["Documento", "Registro", "Acta", "Fotografía", "Reporte de sistema",
                       "Certificado", "Correo"],
    "TIPO_TERCERO": ["Proveedor", "Cliente", "Contratista", "Aliado", "Transportador",
                     "Entidad financiera"],
    "TIPO_SIMULACRO": ["De escritorio", "Funcional", "Completo"],
    "RESULTADO_SIMULACRO": ["Exitoso", "Con observaciones", "Fallido"],
    "SISTEMA_CRITICO": ["ERP", "WMS", "TMS", "Correo electrónico", "Telefonía", "Internet",
                        "Energía eléctrica", "Base de datos", "Facturación electrónica"],
}

# Enums viejos que pasan a catálogo: nombre guardado → valor del catálogo.
ENUM_A_CATALOGO = {
    ("grc_riesgo", "tipo"): {
        "ESTRATEGICO": "Estratégico", "OPERATIVO": "Operativo", "FINANCIERO": "Financiero",
        "TECNOLOGICO": "Tecnológico", "LOGISTICO": "Logístico", "TRANSPORTE": "Transporte",
        "RRHH": "Talento humano", "LEGAL": "Legal", "AMBIENTAL": "Ambiental",
        "REPUTACIONAL": "Reputacional", "CIBERSEGURIDAD": "Ciberseguridad"},
    ("grc_obligacion", "tipo"): {
        "LEY": "Ley", "REGLAMENTO": "Decreto", "NORMA": "Norma técnica", "CONTRATO": "Contrato",
        "POLITICA_INTERNA": "Política interna", "REQUISITO_CLIENTE": "Requisito de cliente"},
    ("grc_auditoria", "tipo"): {
        "INTERNA": "Interna", "EXTERNA": "Externa", "FINANCIERA": "Financiera",
        "OPERATIVA": "Operativa", "TECNOLOGICA": "Tecnológica", "REGULATORIA": "Regulatoria",
        "CUMPLIMIENTO": "De cumplimiento"},
    ("grc_tercero", "tipo"): {
        "PROVEEDOR": "Proveedor", "CLIENTE": "Cliente", "CONTRATISTA": "Contratista", "ALIADO": "Aliado"},
}

# Persona en texto → usuario: (tabla, columna vieja, columna nueva)
PERSONAS = [
    ("grc_comite", "presidente", "presidente_id"), ("grc_comite", "secretario", "secretario_id"),
    ("grc_politica", "propietario", "propietario_id"), ("grc_politica", "aprobador", "aprobador_id"),
    ("grc_obligacion", "responsable", "responsable_id"),
    ("grc_control", "responsable", "responsable_id"),
    ("grc_riesgo", "responsable", "responsable_id"),
    ("grc_tratamiento", "responsable", "responsable_id"),
    ("grc_matriz_cumplimiento", "responsable", "responsable_id"),
    ("grc_evidencia", "responsable", "responsable_id"),
    ("grc_auditoria", "auditor_lider", "auditor_lider_id"),
    ("grc_hallazgo", "responsable", "responsable_id"),
    ("grc_plan_accion", "responsable", "responsable_id"),
    ("grc_incidente", "reportado_por", "reportado_por_id"),
    ("grc_incidente", "responsable", "responsable_id"),
    ("grc_continuidad", "responsable", "responsable_id"),
    ("grc_evaluacion_tercero", "evaluador", "evaluador_id"),
]

# Columnas de texto que pasan a catálogo: (tabla, columna, módulo, tipo)
TEXTO_A_CATALOGO = [
    ("grc_comite", "tipo", "GRC", "TIPO_COMITE"),
    ("grc_comite", "periodicidad", "GRC", "PERIODICIDAD"),
    ("grc_politica", "tipo", "GRC", "TIPO_POLITICA"),
    ("grc_politica", "periodicidad_revision", "GRC", "PERIODICIDAD"),
    ("grc_obligacion", "marco", "GRC", "MARCO_NORMATIVO"),
    ("grc_control", "frecuencia", "GRC", "FRECUENCIA_CONTROL"),
    ("grc_hallazgo", "tipo", "GRC", "TIPO_HALLAZGO"),
    ("grc_incidente", "tipo", "GRC", "TIPO_INCIDENTE"),
    ("grc_evidencia", "tipo", "GRC", "TIPO_EVIDENCIA"),
    ("grc_simulacro", "tipo", "GRC", "TIPO_SIMULACRO"),
    ("grc_simulacro", "resultado", "GRC", "RESULTADO_SIMULACRO"),
]

# Procesos y áreas: si no están en el catálogo compartido, se eliminan. Un
# proceso que nadie definió no sirve para cruzar riesgos con incidentes.
PROCESO_AREA = [
    ("grc_obligacion", "area", "AREA"),
    ("grc_control", "proceso", "PROCESO"), ("grc_control", "area", "AREA"),
    ("grc_riesgo", "proceso", "PROCESO"), ("grc_riesgo", "area", "AREA"),
    ("grc_matriz_cumplimiento", "proceso", "PROCESO"), ("grc_matriz_cumplimiento", "area", "AREA"),
    ("grc_hallazgo", "proceso", "PROCESO"), ("grc_hallazgo", "area", "AREA"),
    ("grc_incidente", "proceso", "PROCESO"), ("grc_incidente", "area", "AREA"),
    ("grc_continuidad", "proceso", "PROCESO"),
]

COLUMNAS_NUEVAS = [
    ("grc_comite", "presidente_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_comite", "secretario_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_comite", "quorum_minimo", "INTEGER"),
    ("grc_politica", "propietario_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_politica", "aprobador_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_obligacion", "marco", "VARCHAR(200)"),
    ("grc_obligacion", "articulo", "VARCHAR(200)"),
    ("grc_obligacion", "proceso", "VARCHAR(200)"),
    ("grc_obligacion", "periodicidad", "VARCHAR(50)"),
    ("grc_obligacion", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_matriz_cumplimiento", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_control", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_control", "periodicidad_prueba", "VARCHAR(50)"),
    ("grc_riesgo", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_riesgo", "causas", "TEXT"),
    ("grc_riesgo", "consecuencias", "TEXT"),
    ("grc_riesgo", "tercero_id", "INTEGER REFERENCES grc_tercero(id) ON DELETE SET NULL"),
    ("grc_riesgo", "fecha_revision", "DATE"),
    ("grc_tratamiento", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_evidencia", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_evidencia", "ruta_archivo", "VARCHAR(500)"),
    ("grc_evidencia", "tamano_bytes", "INTEGER"),
    ("grc_auditoria", "auditor_lider_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_auditoria", "equipo", "JSON"),
    ("grc_auditoria", "proceso", "VARCHAR(200)"),
    ("grc_auditoria", "area", "VARCHAR(200)"),
    ("grc_auditoria", "marco", "VARCHAR(200)"),
    ("grc_hallazgo", "incidente_id", "INTEGER REFERENCES grc_incidente(id) ON DELETE SET NULL"),
    ("grc_hallazgo", "riesgo_id", "INTEGER REFERENCES grc_riesgo(id) ON DELETE SET NULL"),
    ("grc_hallazgo", "control_id", "INTEGER REFERENCES grc_control(id) ON DELETE SET NULL"),
    ("grc_hallazgo", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_hallazgo", "causa_raiz", "TEXT"),
    ("grc_plan_accion", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_incidente", "perdida_estimada", "NUMERIC(15,2)"),
    ("grc_incidente", "riesgo_id", "INTEGER REFERENCES grc_riesgo(id) ON DELETE SET NULL"),
    ("grc_incidente", "control_id", "INTEGER REFERENCES grc_control(id) ON DELETE SET NULL"),
    ("grc_incidente", "reportado_por_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_incidente", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_continuidad", "mtpd_horas", "INTEGER"),
    ("grc_continuidad", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_continuidad", "periodicidad_revision", "VARCHAR(50)"),
    ("grc_simulacro", "coordinador_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_simulacro", "rto_logrado_horas", "INTEGER"),
    ("grc_tercero", "contacto_email", "VARCHAR(200)"),
    ("grc_tercero", "criticidad", "severidadgrcenum"),
    ("grc_tercero", "proveedor_id", "INTEGER REFERENCES proveedores(id) ON DELETE SET NULL"),
    ("grc_tercero", "cliente_id", "INTEGER REFERENCES crm_cliente(id) ON DELETE SET NULL"),
    ("grc_tercero", "responsable_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
    ("grc_evaluacion_tercero", "fecha", "DATE"),
    ("grc_evaluacion_tercero", "evaluador_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL"),
]

# Lo que se elimina por no tener forma coherente.
COLUMNAS_VIEJAS = [
    ("grc_politica", "aceptaciones_count"), ("grc_obligacion", "fuente"),
    ("grc_obligacion", "industria"), ("grc_auditoria", "equipo_auditor"),
    ("grc_auditoria", "auditado"), ("grc_hallazgo", "riesgo_asociado"),
    ("grc_continuidad", "dependencias"),
    # El apetito se fija por categoría en Configuración, no como texto en cada riesgo.
    ("grc_riesgo", "apetito_riesgo"),
]

ESCALA = {
    "probabilidad": [(1, "Rara", "Puede ocurrir solo en circunstancias excepcionales (menos de una vez en 5 años)."),
                     (2, "Improbable", "Podría ocurrir alguna vez (una vez en 2 a 5 años)."),
                     (3, "Posible", "Puede ocurrir (una vez al año)."),
                     (4, "Probable", "Ocurrirá en la mayoría de las circunstancias (varias veces al año)."),
                     (5, "Casi segura", "Se espera que ocurra (mensual o más).")],
    "impacto": [(1, "Insignificante", "Sin efecto apreciable en la operación, las finanzas ni la reputación."),
                (2, "Menor", "Afectación leve y local, se resuelve con recursos normales."),
                (3, "Moderado", "Afecta un proceso o cliente; requiere gestión de la dirección."),
                (4, "Mayor", "Pérdida importante, sanción o afectación a varios clientes."),
                (5, "Catastrófico", "Pone en riesgo la continuidad del negocio o su licencia para operar.")],
}

BANDAS = [("BAJA", 1, "#16A34A", "Se acepta y se monitorea en la revisión periódica."),
          ("MEDIA", 5, "#CA8A04", "Requiere controles y responsable; se revisa cada trimestre."),
          ("ALTA", 10, "#EA580C", "Plan de tratamiento con fecha; seguimiento mensual del comité."),
          ("CRITICA", 15, "#DC2626", "Atención inmediata de la alta dirección; no se acepta.")]

PARAMETROS = {
    "dias_aviso_vencimiento": "30",   # políticas, obligaciones, evidencias
    "dias_aviso_prueba_control": "15",
    "dias_plazo_hallazgo": "60",      # plazo por defecto para cerrar un hallazgo
}

DIAS_PERIODICIDAD = {"Mensual": 30, "Bimestral": 60, "Trimestral": 90, "Semestral": 182,
                     "Anual": 365, "Bianual": 730}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


async def _existe(conn, tabla: str) -> bool:
    return (await conn.execute(text("SELECT to_regclass(:t)"), {"t": tabla})).scalar() is not None


async def _columna(conn, tabla: str, columna: str):
    r = await conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"),
        {"t": tabla, "c": columna})
    return r.scalar()


async def _sembrar_catalogo(conn, modulo: str, tipo: str, nombres) -> None:
    for i, nombre in enumerate(nombres, 1):
        await conn.execute(text("""
            INSERT INTO catalogo_maestro (modulo, tipo, nombre, orden, activo, metadatos, created_at, updated_at)
            SELECT CAST(:m AS VARCHAR), CAST(:t AS VARCHAR), CAST(:n AS VARCHAR), CAST(:o AS INTEGER),
                   true, CAST(:meta AS JSON), now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM catalogo_maestro
                              WHERE modulo = CAST(:m AS VARCHAR) AND tipo = CAST(:t AS VARCHAR)
                                AND lower(nombre) = lower(CAST(:n AS VARCHAR)))
        """), {"m": modulo, "t": tipo, "n": nombre, "o": i,
               "meta": ('{"dias": %d}' % DIAS_PERIODICIDAD[nombre]) if nombre in DIAS_PERIODICIDAD else None})


async def _valores_catalogo(conn, modulo: str, tipo: str) -> dict:
    r = await conn.execute(text(
        "SELECT nombre FROM catalogo_maestro WHERE modulo = :m AND tipo = :t"), {"m": modulo, "t": tipo})
    return {_sin_tildes(n): n for (n,) in r.all()}


async def migrar_grc(conn) -> None:
    if not await _existe(conn, "grc_riesgo") or not await _existe(conn, "catalogo_maestro"):
        return

    # 1. Catálogos GRC. PERIODICIDAD_REVISION se funde en PERIODICIDAD y el
    #    catálogo TIPO_CONTROL se retira: duplicaba la naturaleza del control,
    #    que es metodología fija (preventivo/detectivo/correctivo).
    for tipo, nombres in CATALOGOS_GRC.items():
        await _sembrar_catalogo(conn, "GRC", tipo, nombres)
    await conn.execute(text("""
        INSERT INTO catalogo_maestro (modulo, tipo, nombre, orden, activo, created_at, updated_at)
        SELECT 'GRC', 'PERIODICIDAD', v.nombre, 50, v.activo, now(), now()
        FROM catalogo_maestro v
        WHERE v.modulo = 'GRC' AND v.tipo = 'PERIODICIDAD_REVISION'
          AND NOT EXISTS (SELECT 1 FROM catalogo_maestro p WHERE p.modulo = 'GRC'
                          AND p.tipo = 'PERIODICIDAD' AND lower(p.nombre) = lower(v.nombre))
    """))
    await conn.execute(text(
        "DELETE FROM catalogo_maestro WHERE modulo = 'GRC' AND tipo IN ('PERIODICIDAD_REVISION', 'TIPO_CONTROL')"))
    # La periodicidad lleva sus días para poder calcular la próxima fecha.
    for nombre, dias in DIAS_PERIODICIDAD.items():
        await conn.execute(text(
            "UPDATE catalogo_maestro SET metadatos = CAST(:m AS JSON) WHERE modulo = 'GRC' "
            "AND tipo = 'PERIODICIDAD' AND nombre = :n AND metadatos IS NULL"),
            {"m": '{"dias": %d}' % dias, "n": nombre})

    # 2. Columnas nuevas en tablas que ya existían.
    for tabla, columna, tipo in COLUMNAS_NUEVAS:
        if await _existe(conn, tabla):
            await conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}"))

    # 3. Enums viejos → texto del catálogo.
    for (tabla, columna), mapa in ENUM_A_CATALOGO.items():
        if await _columna(conn, tabla, columna) == "USER-DEFINED":
            casos = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in mapa.items())
            await conn.execute(text(
                f"ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE VARCHAR(100) "
                f"USING (CASE {columna}::text {casos} ELSE NULL END)"))

    # Texto → escala de severidad (criticidad del BIA, urgencia del incidente).
    for tabla, columna in (("grc_continuidad", "criticidad"), ("grc_incidente", "urgencia")):
        if await _columna(conn, tabla, columna) in ("character varying", "text"):
            await conn.execute(text(f"""
                ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE severidadgrcenum
                USING (CASE lower(translate(coalesce({columna}, ''), 'áéíóú', 'aeiou'))
                       WHEN 'critica' THEN 'CRITICA' WHEN 'critico' THEN 'CRITICA'
                       WHEN 'alta' THEN 'ALTA' WHEN 'alto' THEN 'ALTA'
                       WHEN 'media' THEN 'MEDIA' WHEN 'medio' THEN 'MEDIA'
                       WHEN 'baja' THEN 'BAJA' WHEN 'bajo' THEN 'BAJA'
                       ELSE NULL END)::severidadgrcenum"""))

    # 4. Obligación: la «fuente» pasa a ser el marco normativo.
    if await _columna(conn, "grc_obligacion", "fuente"):
        await conn.execute(text(
            "UPDATE grc_obligacion SET marco = fuente WHERE marco IS NULL AND coalesce(trim(fuente), '') <> ''"))
    # Auditoría: lo «auditado» era un proceso o un área escrito a mano.
    if await _columna(conn, "grc_auditoria", "auditado"):
        await conn.execute(text("""
            UPDATE grc_auditoria a SET proceso = c.nombre FROM catalogo_maestro c
            WHERE a.proceso IS NULL AND c.modulo = 'GLOBAL' AND c.tipo = 'PROCESO'
              AND lower(trim(a.auditado)) = lower(c.nombre)"""))
        await conn.execute(text("""
            UPDATE grc_auditoria a SET area = c.nombre FROM catalogo_maestro c
            WHERE a.area IS NULL AND c.modulo = 'GLOBAL' AND c.tipo = 'AREA'
              AND lower(trim(a.auditado)) = lower(c.nombre)"""))

    # 5. Personas en texto → usuarios.
    usuarios = (await conn.execute(text(
        "SELECT id, nombre, apellido, username FROM usuarios"))).all()
    por_nombre = {}
    for uid, nombre, apellido, username in usuarios:
        for clave in (f"{nombre} {apellido}", nombre, username):
            if clave:
                por_nombre.setdefault(_sin_tildes(clave), uid)
    for tabla, vieja, nueva in PERSONAS:
        if not await _columna(conn, tabla, vieja):
            continue
        filas = (await conn.execute(text(
            f"SELECT id, {vieja} FROM {tabla} WHERE {nueva} IS NULL AND coalesce(trim({vieja}), '') <> ''"))).all()
        sin_dueno = 0
        for rid, valor in filas:
            uid = por_nombre.get(_sin_tildes(valor))
            if uid:
                await conn.execute(text(f"UPDATE {tabla} SET {nueva} = :u WHERE id = :i"), {"u": uid, "i": rid})
            else:
                sin_dueno += 1
        if sin_dueno:
            log.warning("GRC: %d valor(es) de %s.%s no corresponden a ningún usuario y se eliminan",
                        sin_dueno, tabla, vieja)
        await conn.execute(text(f"ALTER TABLE {tabla} DROP COLUMN IF EXISTS {vieja}"))

    # Equipo auditor: lista de nombres separados por coma → lista de ids.
    if await _columna(conn, "grc_auditoria", "equipo_auditor"):
        import json
        for rid, valor in (await conn.execute(text(
                "SELECT id, equipo_auditor FROM grc_auditoria WHERE coalesce(trim(equipo_auditor), '') <> ''"))).all():
            ids = [por_nombre[_sin_tildes(p)] for p in valor.replace(";", ",").split(",")
                   if _sin_tildes(p) in por_nombre]
            await conn.execute(text("UPDATE grc_auditoria SET equipo = CAST(:e AS JSON) WHERE id = :i"),
                               {"e": json.dumps(sorted(set(ids))), "i": rid})

    # Riesgo asociado en texto → llave, si nombra un riesgo que existe.
    if await _columna(conn, "grc_hallazgo", "riesgo_asociado"):
        await conn.execute(text("""
            UPDATE grc_hallazgo h SET riesgo_id = r.id FROM grc_riesgo r
            WHERE h.riesgo_id IS NULL AND coalesce(trim(h.riesgo_asociado), '') <> ''
              AND (lower(trim(h.riesgo_asociado)) = lower(r.codigo)
                   OR lower(trim(h.riesgo_asociado)) = lower(r.nombre))"""))

    # 6. Clasificaciones en texto → catálogo (se normalizan o se agregan).
    for tabla, columna, modulo, tipo in TEXTO_A_CATALOGO:
        if await _columna(conn, tabla, columna) not in ("character varying", "text"):
            continue
        conocidos = await _valores_catalogo(conn, modulo, tipo)
        for (valor,) in (await conn.execute(text(
                f"SELECT DISTINCT {columna} FROM {tabla} WHERE coalesce(trim({columna}), '') <> ''"))).all():
            canon = conocidos.get(_sin_tildes(valor))
            if canon is None:
                canon = valor.strip()[:1].upper() + valor.strip()[1:]
                await _sembrar_catalogo(conn, modulo, tipo, [canon])
                conocidos[_sin_tildes(canon)] = canon
            if canon != valor:
                await conn.execute(text(f"UPDATE {tabla} SET {columna} = :c WHERE {columna} = :v"),
                                   {"c": canon, "v": valor})
    # Sistemas críticos: texto separado por comas → lista del catálogo.
    if await _columna(conn, "grc_continuidad", "sistemas_criticos") == "text":
        import json
        conocidos = await _valores_catalogo(conn, "GRC", "SISTEMA_CRITICO")
        filas = (await conn.execute(text(
            "SELECT id, sistemas_criticos FROM grc_continuidad"))).all()
        await conn.execute(text("ALTER TABLE grc_continuidad DROP COLUMN sistemas_criticos"))
        await conn.execute(text("ALTER TABLE grc_continuidad ADD COLUMN sistemas_criticos JSON"))
        for rid, valor in filas:
            lista = []
            for parte in (valor or "").replace(";", ",").replace("\n", ",").split(","):
                if not parte.strip():
                    continue
                canon = conocidos.get(_sin_tildes(parte))
                if canon is None:
                    canon = parte.strip()
                    await _sembrar_catalogo(conn, "GRC", "SISTEMA_CRITICO", [canon])
                    conocidos[_sin_tildes(canon)] = canon
                lista.append(canon)
            await conn.execute(text("UPDATE grc_continuidad SET sistemas_criticos = CAST(:l AS JSON) WHERE id = :i"),
                               {"l": json.dumps(lista, ensure_ascii=False), "i": rid})

    # Participantes del simulacro: era un número suelto, no personas.
    if await _columna(conn, "grc_simulacro", "participantes") == "integer":
        await conn.execute(text("ALTER TABLE grc_simulacro DROP COLUMN participantes"))
        await conn.execute(text("ALTER TABLE grc_simulacro ADD COLUMN participantes JSON"))

    # 7. Procesos y áreas que no existen en el catálogo compartido → se eliminan.
    for tabla, columna, tipo in PROCESO_AREA:
        if await _columna(conn, tabla, columna) not in ("character varying", "text"):
            continue
        conocidos = await _valores_catalogo(conn, "GLOBAL", tipo)
        for (valor,) in (await conn.execute(text(
                f"SELECT DISTINCT {columna} FROM {tabla} WHERE {columna} IS NOT NULL"))).all():
            canon = conocidos.get(_sin_tildes(valor))
            if canon != valor:
                if tabla == "grc_continuidad" and canon is None:
                    # El proceso es la identidad del plan de continuidad: se
                    # agrega al catálogo en vez de dejar el plan sin proceso.
                    await _sembrar_catalogo(conn, "GLOBAL", tipo, [valor.strip()])
                    continue
                await conn.execute(text(f"UPDATE {tabla} SET {columna} = :c WHERE {columna} = :v"),
                                   {"c": canon, "v": valor})

    # 8. Lo que no tiene forma coherente.
    for tabla, columna in COLUMNAS_VIEJAS:
        if await _existe(conn, tabla):
            await conn.execute(text(f"ALTER TABLE {tabla} DROP COLUMN IF EXISTS {columna}"))
    await conn.execute(text("DROP TABLE IF EXISTS grc_kpi_diario"))
    for tipo in ("tiporiesgogrcenum", "tipoobligaciongrcenum", "tipoauditoriagrcenum", "tipotercerogrcenum"):
        # Solo si ya ninguna columna lo usa en este esquema.
        en_uso = (await conn.execute(text("""
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = current_schema() AND udt_name = :t"""), {"t": tipo})).scalar()
        if not en_uso:
            await conn.execute(text(f"DROP TYPE IF EXISTS {tipo}"))

    # 9. Matriz, bandas y parámetros por defecto (solo si faltan).
    for eje, niveles in ESCALA.items():
        for valor, nombre, desc in niveles:
            await conn.execute(text("""
                INSERT INTO grc_escala (eje, valor, nombre, descripcion, created_at, updated_at)
                VALUES (:e, :v, :n, :d, now(), now()) ON CONFLICT (eje, valor) DO NOTHING"""),
                {"e": eje, "v": valor, "n": nombre, "d": desc})
    for prioridad, minimo, color, respuesta in BANDAS:
        await conn.execute(text("""
            INSERT INTO grc_banda_riesgo (prioridad, minimo, color, respuesta, created_at, updated_at)
            VALUES (CAST(:p AS prioridadriesgogrcenum), :m, :c, :r, now(), now())
            ON CONFLICT (prioridad) DO NOTHING"""), {"p": prioridad, "m": minimo, "c": color, "r": respuesta})
    for clave, valor in PARAMETROS.items():
        await conn.execute(text("""
            INSERT INTO grc_parametro (clave, valor, created_at, updated_at)
            VALUES (:c, :v, now(), now()) ON CONFLICT (clave) DO NOTHING"""), {"c": clave, "v": valor})
