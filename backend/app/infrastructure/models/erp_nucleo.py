"""
El núcleo contable: lo que le faltaba al ERP para dejar de ser un registro de
documentos y ser contabilidad.

Va aparte de `erp.py` —que ya pasa de 670 líneas y cubre los documentos— pero es
el MISMO módulo: estas tablas se relacionan con las que ya existen y no las
duplican. Lo que había servía para registrar facturas y comprobantes; lo que
faltaba era lo que hace que esos registros sean confiables.

Los cinco huecos que esto cierra, y por qué cada uno importa:

  1. **Terceros.** Hoy un cliente es una cadena de texto: `cliente_nombre`. Sin
     NIT no hay exógena, no hay cartera por tercero que cuadre, y «Juan Pérez» y
     «JUAN PEREZ» son dos personas distintas. Es el hueco más caro de todos
     porque contamina todo lo que se construya encima.

  2. **Períodos.** Nada impedía contabilizar en un mes ya declarado. Un asiento
     que entra a un período cerrado invalida una declaración presentada.

  3. **Reglas contables.** Los códigos de cuenta estaban escritos dentro de los
     endpoints —«130505», «413500»—. Cambiar el PUC exigía desplegar, y cada
     empresa que use un plan distinto necesitaba su propia versión del software.

  4. **Reglas de impuesto.** Un impuesto era un porcentaje plano. Sin vigencia,
     una tarifa que cambia reescribe el pasado; sin base mínima ni municipio, ni
     el ICA ni la retención en la fuente se pueden calcular bien.

  5. **Auditoría.** La tabla ya existía —`erp_auditoria` en `erp.py`— pero sin
     empresa, sin motivo y sin decir de qué documento salió cada cosa. Se le
     agregan esas tres columnas en vez de crear una segunda tabla: dos registros
     de auditoría para el mismo módulo son dos versiones de la verdad.

Nada de esto inventa datos. Lo que no se pueda resolver todavía —la DIAN, los
bancos— queda como interfaz declarada, no como pantalla que finge.
"""
import enum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.models.base import Base, TimestampMixin, SoftDeleteMixin


# ─── Vocabulario ──────────────────────────────────────────────────────────────
#
# Como texto y no como enum de PostgreSQL: agregar un valor a un enum de base
# exige un ALTER TYPE, y estas listas están hechas para crecer.

class TipoIdentificacion(str, enum.Enum):
    """Los del RUT. El NIT lleva dígito de verificación; los demás no."""
    NIT = "NIT"
    CC = "CC"
    CE = "CE"
    TI = "TI"
    PASAPORTE = "PASAPORTE"
    PEP = "PEP"
    NIT_EXTRANJERO = "NIT_EXTRANJERO"
    SIN_IDENTIFICACION = "SIN_IDENTIFICACION"


class TipoTercero(str, enum.Enum):
    CLIENTE = "CLIENTE"
    PROVEEDOR = "PROVEEDOR"
    EMPLEADO = "EMPLEADO"
    SOCIO = "SOCIO"
    ENTIDAD = "ENTIDAD"
    OTRO = "OTRO"


class EstadoPeriodo(str, enum.Enum):
    ABIERTO = "ABIERTO"
    # Cerrado: no admite movimiento. Se puede reabrir con permiso y queda
    # constancia de quién lo hizo y por qué.
    CERRADO = "CERRADO"
    # Bloqueado definitivo: el cierre anual, una vez presentada la declaración.
    BLOQUEADO = "BLOQUEADO"


# ─── Terceros ─────────────────────────────────────────────────────────────────

class ERPTercero(Base, TimestampMixin, SoftDeleteMixin):
    """El maestro de terceros: quién es la otra parte de cada transacción.

    Es el cimiento de la información exógena, de la cartera por tercero y de las
    retenciones: sin NIT no se puede reportar a nadie, y sin responsabilidades
    tributarias no se puede saber si se le practica retención.

    Un tercero puede ser cliente Y proveedor a la vez —pasa todo el tiempo— así
    que los papeles son marcas y no un tipo excluyente.
    """

    __tablename__ = "erp_terceros"
    __table_args__ = (
        # Un NIT no se repite dentro de una empresa. Sin esto, el mismo
        # proveedor entra dos veces y la exógena lo reporta partido.
        sa.UniqueConstraint("empresa_id", "numero_identificacion",
                            name="uq_erp_tercero_ident"),
        sa.Index("ix_erp_tercero_busca", "empresa_id", "razon_social"),
        sa.Index("ix_erp_tercero_nit", "numero_identificacion"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)

    # ── Identificación ──
    tipo_identificacion = sa.Column(sa.String(30), nullable=False, default="NIT")
    numero_identificacion = sa.Column(sa.String(30), nullable=False)
    # El dígito de verificación se CALCULA, no se pide: pedirlo es invitar a que
    # alguien lo escriba mal, y un DV equivocado hace rechazar la exógena entera.
    digito_verificacion = sa.Column(sa.String(1))

    razon_social = sa.Column(sa.String(300), nullable=False)
    nombre_comercial = sa.Column(sa.String(300))
    # Para personas naturales; en jurídicas van vacíos y manda la razón social.
    primer_nombre = sa.Column(sa.String(80))
    otros_nombres = sa.Column(sa.String(80))
    primer_apellido = sa.Column(sa.String(80))
    segundo_apellido = sa.Column(sa.String(80))
    es_persona_natural = sa.Column(sa.Boolean, default=False, nullable=False)

    # ── Qué papel juega ──
    es_cliente = sa.Column(sa.Boolean, default=False, nullable=False)
    es_proveedor = sa.Column(sa.Boolean, default=False, nullable=False)
    es_empleado = sa.Column(sa.Boolean, default=False, nullable=False)
    es_socio = sa.Column(sa.Boolean, default=False, nullable=False)

    # ── Contacto ──
    direccion = sa.Column(sa.String(300))
    ciudad = sa.Column(sa.String(120))
    # Código DANE del municipio. Es lo que decide la tarifa de ICA, así que va
    # como código y no como nombre: «Bogotá» y «Bogotá D.C.» no se cruzan solos.
    codigo_municipio = sa.Column(sa.String(10))
    departamento = sa.Column(sa.String(120))
    codigo_departamento = sa.Column(sa.String(5))
    pais = sa.Column(sa.String(80), default="Colombia")
    telefono = sa.Column(sa.String(60))
    email = sa.Column(sa.String(200))

    # ── Tributario ──
    # Las responsabilidades del RUT, por su código: O-13, O-15, O-23, O-47…
    # Van en jsonb porque la lista la cambia la DIAN y una columna por
    # responsabilidad obligaría a migrar cada vez.
    responsabilidades = sa.Column(JSONB, default=list, nullable=False)
    regimen = sa.Column(sa.String(40))          # RESPONSABLE_IVA, NO_RESPONSABLE, SIMPLE
    codigo_ciiu = sa.Column(sa.String(10))
    # Marcas que deciden si se le practica o no cada retención. Se guardan acá y
    # no se deducen del régimen porque hay excepciones: un gran contribuyente
    # autorretenedor no soporta retención de renta.
    autorretenedor = sa.Column(sa.Boolean, default=False, nullable=False)
    gran_contribuyente = sa.Column(sa.Boolean, default=False, nullable=False)
    agente_retencion = sa.Column(sa.Boolean, default=False, nullable=False)
    exento_retencion = sa.Column(sa.Boolean, default=False, nullable=False)

    # ── Comercial ──
    dias_credito = sa.Column(sa.Integer, default=0, nullable=False)
    cupo_credito = sa.Column(sa.Numeric(18, 2), default=0)
    # Las cuentas que usa este tercero cuando difieren de las del catálogo
    # general. Vacías = se usan las que diga la regla contable.
    cuenta_cxc_id = sa.Column(sa.Integer, sa.ForeignKey("erp_plan_cuentas.id"))
    cuenta_cxp_id = sa.Column(sa.Integer, sa.ForeignKey("erp_plan_cuentas.id"))

    # ── Bancario, para dispersión de pagos ──
    banco_nombre = sa.Column(sa.String(120))
    banco_tipo_cuenta = sa.Column(sa.String(20))
    banco_numero_cuenta = sa.Column(sa.String(40))

    notas = sa.Column(sa.Text)
    activo = sa.Column(sa.Boolean, default=True, nullable=False)

    # De dónde salió. Un tercero puede venir del CRM, de proveedores o crearse
    # acá; saberlo evita crear el mismo dos veces al integrar otro módulo.
    origen = sa.Column(sa.String(30), default="ERP")
    origen_id = sa.Column(sa.Integer)


# ─── Períodos contables ───────────────────────────────────────────────────────

class ERPPeriodo(Base, TimestampMixin):
    """Un mes contable, con su estado.

    Sin esto, un asiento puede entrar a un mes ya declarado y dejar la
    declaración presentada sin respaldo. El período es lo que convierte la
    contabilidad en algo que se puede cerrar y firmar.
    """

    __tablename__ = "erp_periodos"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "anio", "mes", name="uq_erp_periodo"),
        sa.Index("ix_erp_periodo_busca", "empresa_id", "anio", "mes"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)

    anio = sa.Column(sa.Integer, nullable=False)
    # 0 = el período de apertura del año, donde entran los saldos iniciales.
    # 13 = el de cierre, donde se cancelan las cuentas de resultado. Separarlos
    # de los doce meses es lo que permite que el libro mayor de diciembre no
    # mezcle el movimiento del mes con el asiento de cierre.
    mes = sa.Column(sa.Integer, nullable=False)

    estado = sa.Column(sa.String(20), default="ABIERTO", nullable=False)

    cerrado_por = sa.Column(sa.String(120))
    cerrado_en = sa.Column(sa.DateTime(timezone=True))
    # Por qué se reabrió. Reabrir sin justificar es lo mismo que no cerrar.
    motivo_reapertura = sa.Column(sa.Text)
    reabierto_por = sa.Column(sa.String(120))
    reabierto_en = sa.Column(sa.DateTime(timezone=True))


# ─── Reglas contables ─────────────────────────────────────────────────────────

class ERPReglaContable(Base, TimestampMixin):
    """Qué cuentas usa cada evento del ERP.

    Es lo que saca los códigos de cuenta de dentro del código. Antes, facturar
    escribía «130505» en el endpoint: cambiar el PUC exigía desplegar, y una
    empresa con otro plan necesitaba otra versión del software.

    El destino de cada línea se nombra por su PAPEL —«cartera», «ingreso»,
    «iva_generado»— y la regla dice qué cuenta cumple ese papel. Así el motor
    contable no sabe de números de cuenta, solo de papeles.
    """

    __tablename__ = "erp_reglas_contables"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "evento", "papel", "condicion",
                            name="uq_erp_regla_contable"),
        sa.Index("ix_erp_regla_evento", "empresa_id", "evento"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)

    # El evento del ERP: VENTA_FACTURA, COMPRA_FACTURA, PAGO_PROVEEDOR,
    # RECAUDO_CLIENTE, INVENTARIO_SALIDA, NOMINA_LIQUIDACION, ACTIVO_DEPRECIACION…
    evento = sa.Column(sa.String(60), nullable=False)
    # El papel de la línea dentro del asiento: cartera, ingreso, iva_generado,
    # retefuente, costo_venta, inventario, banco, proveedor…
    papel = sa.Column(sa.String(60), nullable=False)
    # Un discriminante opcional para cuando el mismo papel usa cuentas distintas
    # según algo —la línea de producto, el tipo de servicio—. Vacío = la regla
    # general, que es la que se usa si no hay una más específica.
    condicion = sa.Column(sa.String(60), default="", nullable=False)

    cuenta_id = sa.Column(sa.Integer, sa.ForeignKey("erp_plan_cuentas.id"),
                          nullable=False)
    # DEBITO o CREDITO. Va en la regla y no en el código: hay eventos donde el
    # mismo papel invierte su naturaleza —una nota crédito frente a una factura—.
    naturaleza = sa.Column(sa.String(10), nullable=False)

    descripcion = sa.Column(sa.String(300))
    activa = sa.Column(sa.Boolean, default=True, nullable=False)


# ─── Motor tributario ─────────────────────────────────────────────────────────

class ERPReglaImpuesto(Base, TimestampMixin):
    """Una regla tributaria con vigencia.

    Un impuesto no es un porcentaje: es un porcentaje que aplica a ciertos
    conceptos, sobre cierta base mínima, en cierto municipio, durante cierto
    tiempo. Guardarlo como un número plano hace dos daños: cuando la tarifa
    cambia se reescribe el pasado, y no hay forma de calcular ICA ni retención en
    la fuente, que dependen del concepto y del municipio.

    Las tarifas y las bases se actualizan por configuración. No se codifican acá
    valores que la DIAN puede cambiar cada año.
    """

    __tablename__ = "erp_reglas_impuesto"
    __table_args__ = (
        sa.Index("ix_erp_regla_imp_busca", "empresa_id", "impuesto", "vigente_desde"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)

    # IVA, RETEFUENTE, RETEIVA, RETEICA, ICA, AUTORRETENCION, IMPOCONSUMO
    impuesto = sa.Column(sa.String(30), nullable=False)
    # El concepto: «compras generales», «servicios», «honorarios», «arrendamientos».
    # Es lo que decide la tarifa de retención, y por eso no puede ser un texto
    # libre en la factura.
    concepto = sa.Column(sa.String(120), nullable=False)
    codigo_concepto = sa.Column(sa.String(20))

    tarifa = sa.Column(sa.Numeric(9, 4), nullable=False, default=0)
    # En UVT y en pesos. Se guardan las dos porque la norma habla en UVT pero la
    # comparación se hace en pesos, y el valor de la UVT cambia cada año.
    base_minima_uvt = sa.Column(sa.Numeric(12, 2), default=0)
    base_minima_pesos = sa.Column(sa.Numeric(18, 2), default=0)

    # ── Cuándo aplica ──
    vigente_desde = sa.Column(sa.Date, nullable=False)
    # Vacío = sigue vigente. Al crear una regla nueva del mismo concepto se le
    # pone fecha de fin a la anterior, en vez de editarla: editar la vieja
    # reescribiría cómo se calculó lo que ya se declaró.
    vigente_hasta = sa.Column(sa.Date)

    # ── A quién y dónde ──
    # Vacío = a todos. Con valor, solo a los que cumplan.
    codigo_municipio = sa.Column(sa.String(10))
    codigo_ciiu = sa.Column(sa.String(10))
    aplica_regimen = sa.Column(sa.String(40))
    # Si el tercero es autorretenedor no se le practica; si es gran
    # contribuyente, algunas sí y otras no.
    excluye_autorretenedor = sa.Column(sa.Boolean, default=True, nullable=False)
    excluye_gran_contribuyente = sa.Column(sa.Boolean, default=False, nullable=False)

    # ── Contabilización ──
    cuenta_id = sa.Column(sa.Integer, sa.ForeignKey("erp_plan_cuentas.id"))
    # El papel con el que entra al asiento: iva_generado, iva_descontable,
    # retefuente_practicada, retefuente_soportada…
    papel = sa.Column(sa.String(60))

    descripcion = sa.Column(sa.String(300))
    activa = sa.Column(sa.Boolean, default=True, nullable=False)


class ERPParametroFiscal(Base, TimestampMixin):
    """Los valores que cambian cada año: UVT, salario mínimo, auxilio.

    Van en tabla y no como constantes porque cambian todos los eneros, y una
    constante en el código obliga a desplegar para poder facturar en enero.
    """

    __tablename__ = "erp_parametros_fiscales"
    __table_args__ = (
        sa.UniqueConstraint("anio", "clave", name="uq_erp_parametro_fiscal"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    anio = sa.Column(sa.Integer, nullable=False)
    clave = sa.Column(sa.String(40), nullable=False)   # UVT, SMMLV, AUX_TRANSPORTE
    valor = sa.Column(sa.Numeric(18, 2), nullable=False)
    descripcion = sa.Column(sa.String(200))
    # De dónde salió el valor: la resolución que lo fijó. Sin esto, nadie puede
    # comprobar de dónde vino una cifra dos años después.
    fuente = sa.Column(sa.String(200))


# ─── Trazabilidad ─────────────────────────────────────────────────────────────

# ─── El puente con los demás módulos ──────────────────────────────────────────

class ERPEventoContable(Base):
    """Un hecho económico que ocurrió en otro módulo y espera contabilización.

    Es lo que desacopla Finanzas del resto: ventas, inventarios o nómina
    registran QUE pasó algo, y el motor contable decide qué asiento produce. Sin
    esta cola, cada módulo tendría que saber de cuentas contables, y cambiar el
    PUC obligaría a tocar los seis.

    Se guarda el evento aunque falle su contabilización. Perder el hecho porque
    la regla estaba mal configurada es perder información real por un problema de
    parametrización.
    """

    __tablename__ = "erp_eventos_contables"
    __table_args__ = (
        sa.Index("ix_erp_evento_pendiente", "empresa_id", "estado", "fecha"),
        sa.Index("ix_erp_evento_origen", "modulo", "documento_tipo", "documento_id"),
    )

    id = sa.Column(sa.BigInteger, primary_key=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)

    # De dónde viene: VENTAS, COMPRAS, INVENTARIO, NOMINA, TESORERIA, ACTIVOS,
    # TMS, WMS, EAM…
    modulo = sa.Column(sa.String(30), nullable=False)
    evento = sa.Column(sa.String(60), nullable=False)

    # El documento que lo originó, para poder volver de un asiento a su fuente.
    documento_tipo = sa.Column(sa.String(60), nullable=False)
    documento_id = sa.Column(sa.Integer, nullable=False)
    documento_numero = sa.Column(sa.String(60))

    fecha = sa.Column(sa.Date, nullable=False)
    tercero_id = sa.Column(sa.Integer, sa.ForeignKey("erp_terceros.id"))
    centro_costo_id = sa.Column(sa.Integer, sa.ForeignKey("erp_centros_costo.id"))

    # Los importes por papel: {"ingreso": 1000000, "iva_generado": 190000}. El
    # módulo de origen no sabe de cuentas; solo dice cuánto va en cada papel.
    importes = sa.Column(JSONB, default=dict, nullable=False)
    moneda = sa.Column(sa.String(3), default="COP", nullable=False)
    tasa_cambio = sa.Column(sa.Numeric(18, 6), default=1)

    # PENDIENTE · CONTABILIZADO · FALLIDO · IGNORADO
    estado = sa.Column(sa.String(20), default="PENDIENTE", nullable=False)
    comprobante_id = sa.Column(sa.Integer, sa.ForeignKey("erp_comprobantes.id"))
    # Por qué falló. Se guarda el motivo y no solo el estado: «falló» sin motivo
    # obliga a reproducir el error para saber qué configurar.
    error = sa.Column(sa.Text)
    intentos = sa.Column(sa.Integer, default=0, nullable=False)

    creado = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                       nullable=False)
    procesado = sa.Column(sa.DateTime(timezone=True))


class ERPConsecutivo(Base, TimestampMixin):
    """El último número usado de cada talonario.

    Existe por desempeño y no por prolijidad. Deducir el consecutivo del máximo
    de los comprobantes ya emitidos obliga a releerlos todos cada vez que se
    emite uno nuevo, y ningún índice ayuda porque el número está dentro de una
    cadena. El costo crece con el uso: es imperceptible el primer mes e
    insoportable el tercer año.

    Con una fila por talonario, `UPDATE ... RETURNING` da el siguiente número en
    tiempo constante, y el bloqueo de esa fila serializa —por sí solo— a quienes
    numeran el MISMO talonario sin estorbar a los demás.
    """

    __tablename__ = "erp_consecutivos"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "prefijo", "anio", name="uq_erp_consecutivo"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"), nullable=False)
    # CD, RC, CE… El prefijo y no el tipo, porque varios tipos pueden compartir
    # talonario si la empresa así lo lleva.
    prefijo = sa.Column(sa.String(8), nullable=False)
    anio = sa.Column(sa.Integer, nullable=False)
    ultimo = sa.Column(sa.Integer, nullable=False, default=0)
