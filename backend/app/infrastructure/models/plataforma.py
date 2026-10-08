"""
Registro de clientes de la plataforma.

Vive en el esquema `public` y no dentro del de cada cliente: hay que poder
consultarlo en el paso previo al login, cuando todavía no se sabe a qué cliente
se está entrando.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, Date, Text, JSON
from app.infrastructure.models.base import Base, TimestampMixin
from app.core.tenant import ESQUEMA_PLATAFORMA


class PlataformaCliente(Base, TimestampMixin):
    """Una empresa que usa la plataforma.

    `codigo` es lo que se escribe en la pantalla previa al login y lo que
    determina el esquema donde viven sus datos, así que no se puede cambiar
    después: sus tablas quedarían huérfanas.
    """

    __tablename__ = "plataforma_cliente"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id       = Column(Integer, primary_key=True, index=True)
    codigo   = Column(String(40), unique=True, nullable=False, index=True)
    nombre   = Column(String(200), nullable=False)
    esquema  = Column(String(60), unique=True, nullable=False)
    # Identidad visual de cada cliente en su propio portal.
    logo_url = Column(String(400))
    color    = Column(String(20))
    nit      = Column(String(30))
    activo   = Column(Boolean, default=True)
    # Quien opera la plataforma: da de alta y suspende a las demás empresas.
    # Va acá, fuera de los esquemas, para que ningún cliente pueda otorgárselo.
    es_operador = Column(Boolean, default=False)
    # Se apaga el acceso sin borrar los datos.
    suspendido_desde = Column(DateTime)


class PlataformaBitacora(Base):
    """Lo que el operador hace sobre las empresas y sus usuarios.

    El operador puede crear usuarios dentro de cualquier empresa y restablecer
    sus claves, que es poder suficiente para entrar a la cuenta de un cliente.
    Ese poder hace falta para dar soporte, pero tiene que dejar rastro: sin esta
    tabla no habría forma de saber, después, quién entró a qué.

    Vive en `public` junto al registro y no dentro del esquema del cliente: si
    estuviera allí, el propio operador podría borrar su rastro con las mismas
    credenciales con las que actuó.
    """

    __tablename__ = "plataforma_bitacora"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id      = Column(Integer, primary_key=True, index=True)
    fecha   = Column(DateTime, nullable=False, index=True)
    # Quién actuó: el usuario y la empresa desde la que lo hizo.
    actor           = Column(String(80), nullable=False)
    actor_empresa   = Column(String(40), nullable=False)
    # Qué hizo y sobre qué empresa.
    accion          = Column(String(60), nullable=False, index=True)
    empresa_codigo  = Column(String(40), index=True)
    # Texto libre con lo que distingue a esta acción de otra igual.
    detalle         = Column(String(500))


# ─── La relación comercial con cada empresa ───────────────────────────────────
#
# Todo esto vive en `public`, junto al registro, porque es información *del
# operador sobre* el cliente —lo que paga, qué firmó, a quién llamar— y no
# información del cliente. Guardarla dentro del esquema de cada empresa la
# dejaría a la vista de esa misma empresa.


class PlataformaContrato(Base, TimestampMixin):
    """Lo que una empresa paga y bajo qué condiciones. Uno por empresa."""

    __tablename__ = "plataforma_contrato"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, unique=True, index=True)

    # Tarifa plana por empresa, no por usuario: el número de usuarios cambia
    # todos los meses y facturar sobre él obliga a conciliar cada corte.
    tarifa_mensual = Column(Numeric(14, 2), default=0)
    moneda         = Column(String(3), default="COP")
    # Configurable porque no todos los clientes son responsables de IVA.
    iva_pct        = Column(Numeric(5, 2), default=19)
    # Día del mes en que se factura.
    dia_corte      = Column(Integer, default=1)

    inicio = Column(Date)
    fin    = Column(Date)   # vacío = sin fecha de terminación pactada

    notas = Column(Text)


class PlataformaModuloCliente(Base):
    """Qué módulos tiene contratados una empresa.

    No es una lista decorativa: el servidor la hace cumplir en cada petición,
    así que un módulo que no está acá no se puede usar aunque se escriba la URL
    a mano.
    """

    __tablename__ = "plataforma_modulo_cliente"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)
    modulo     = Column(String(40), nullable=False, index=True)
    activo     = Column(Boolean, default=True)
    desde      = Column(Date)


class PlataformaContacto(Base, TimestampMixin):
    """A quién llamar en esa empresa."""

    __tablename__ = "plataforma_contacto"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)
    nombre     = Column(String(150), nullable=False)
    cargo      = Column(String(120))
    email      = Column(String(200))
    telefono   = Column(String(40))
    # El contacto al que se le escribe si no se dice otra cosa.
    principal  = Column(Boolean, default=False)
    notas      = Column(String(400))


class PlataformaDocumento(Base, TimestampMixin):
    """Los papeles del cliente: contrato, RUT, cámara de comercio.

    Se guarda la referencia y no el archivo: los adjuntos van al disco por el
    mismo camino que el resto de la plataforma.
    """

    __tablename__ = "plataforma_documento"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)
    tipo       = Column(String(60))           # contrato, RUT, cámara de comercio…
    nombre     = Column(String(200), nullable=False)
    archivo    = Column(String(400))          # ruta relativa dentro de UPLOAD_DIR
    # Para avisar antes de que se venza, no después.
    vence      = Column(Date)
    notas      = Column(String(400))


class PlataformaPago(Base, TimestampMixin):
    """Un pago recibido, con el periodo que cubre.

    El periodo se guarda explícito y no se deduce de la fecha del pago: los
    clientes pagan tarde, adelantado y a veces varios meses juntos, y sin él no
    hay forma de saber hasta cuándo está cubierta una empresa.
    """

    __tablename__ = "plataforma_pago"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)
    # A qué factura se aplica. Puede ir vacío: hay pagos anteriores a que
    # existieran facturas, y también anticipos que todavía no tienen una.
    factura_id = Column(Integer, index=True)
    fecha      = Column(Date, nullable=False, index=True)
    monto      = Column(Numeric(14, 2), nullable=False)
    moneda     = Column(String(3), default="COP")
    periodo_desde = Column(Date)
    periodo_hasta = Column(Date, index=True)
    metodo     = Column(String(40))           # transferencia, efectivo, PSE…
    referencia = Column(String(120))          # número de factura o comprobante
    notas      = Column(String(400))


# ─── La cadena contable: factura → nota crédito → pago ────────────────────────
#
# AVISO IMPORTANTE: esto es control contable interno, NO facturación electrónica
# ante la DIAN. No genera CUFE ni valida rangos de numeración autorizados. La
# factura legal se emite en el proveedor de facturación electrónica y su número
# se guarda acá, en `numero_externo`, para poder cruzar las dos cosas.


class PlataformaFactura(Base, TimestampMixin):
    """Lo que se le cobró a una empresa por un periodo."""

    __tablename__ = "plataforma_factura"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)

    # Consecutivo interno de la plataforma.
    numero         = Column(String(30), nullable=False, unique=True, index=True)
    # El número de la factura electrónica real, para cruzar con la contabilidad.
    numero_externo = Column(String(40))

    fecha         = Column(Date, nullable=False, index=True)
    periodo_desde = Column(Date)
    periodo_hasta = Column(Date, index=True)

    # Se congelan los valores en vez de recalcularlos desde el contrato: si la
    # tarifa sube el mes que viene, lo ya facturado no puede cambiar solo.
    subtotal  = Column(Numeric(14, 2), nullable=False, default=0)
    iva_pct   = Column(Numeric(5, 2), default=19)
    iva_valor = Column(Numeric(14, 2), default=0)
    total     = Column(Numeric(14, 2), nullable=False, default=0)
    moneda    = Column(String(3), default="COP")

    # Anulada = sin efecto contable. No se borra: una factura emitida que
    # desaparece deja un hueco en el consecutivo y nadie puede explicarlo.
    anulada   = Column(Boolean, default=False)
    concepto  = Column(String(300))
    notas     = Column(String(400))


class PlataformaNotaCredito(Base, TimestampMixin):
    """Rebaja o anula parte de una factura ya emitida.

    Existe porque una factura emitida no se corrige editándola: se emite una
    nota crédito que la disminuye, y las dos quedan en el historial. Así el
    consecutivo y lo ya reportado siguen cuadrando.
    """

    __tablename__ = "plataforma_nota_credito"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, nullable=False, index=True)
    factura_id = Column(Integer, nullable=False, index=True)

    numero         = Column(String(30), nullable=False, unique=True, index=True)
    numero_externo = Column(String(40))

    fecha  = Column(Date, nullable=False, index=True)
    valor  = Column(Numeric(14, 2), nullable=False)
    moneda = Column(String(3), default="COP")
    # Por qué se emitió: es lo primero que se pregunta al revisar la cuenta.
    motivo = Column(String(300), nullable=False)
    notas  = Column(String(400))


class PlataformaMiembro(Base, TimestampMixin):
    """Quién del equipo entra a la consola y con qué rol.

    Va aparte de `usuarios` porque son dos cosas distintas: `usuarios` dice
    quién puede entrar a la plataforma de la empresa operadora; esto dice quién
    además administra la plataforma entera y hasta dónde llega.

    Sin esta separación, cualquier administrador de la empresa operadora tenía
    acceso total a la consola por el solo hecho de ser administrador de su
    propia empresa.
    """

    __tablename__ = "plataforma_miembro"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id      = Column(Integer, primary_key=True, index=True)
    # El `username` dentro del esquema de la empresa operadora.
    usuario = Column(String(80), unique=True, nullable=False, index=True)
    nombre  = Column(String(160))
    email   = Column(String(200))
    rol     = Column(String(30), nullable=False, default="CONSULTA")
    activo  = Column(Boolean, default=True)
    notas   = Column(String(300))


class PlataformaLanding(Base, TimestampMixin):
    """El contenido de la landing pública.

    Un solo documento JSON y no una columna por párrafo: los textos de una
    página cambian de forma cada vez que se rediseña, y con columnas habría que
    migrar la base cada vez que alguien mueve una sección.
    """

    __tablename__ = "plataforma_landing"
    __table_args__ = {"schema": ESQUEMA_PLATAFORMA}

    id              = Column(Integer, primary_key=True, index=True)
    contenido       = Column(JSON)
    actualizado_por = Column(String(80))
