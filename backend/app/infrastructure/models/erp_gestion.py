"""
Lo que les faltaba a las pantallas de gestión para dejar de ser maqueta.

Tres cosas que se dibujaban con números fijos en el código y ahora se guardan:
los escenarios de planeación, los inductores del costeo ABC y el resultado de
cada distribución de costos indirectos.

El criterio para que algo llegue acá es que **alguien lo decida y otro lo tenga
que poder revisar después**. Un escenario de planeación es una decisión: quién
supuso qué crecimiento, cuándo, y qué salió. Un inductor ABC también: repartir el
arriendo por metros cuadrados o por horas hombre cambia qué línea de negocio
parece rentable, y eso no puede vivir en una constante del frontend donde nadie
lo ve ni lo discute.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.infrastructure.models.base import TimestampMixin


class ERPEscenario(Base, TimestampMixin):
    """Una proyección con sus supuestos, guardada.

    Se guarda el SUPUESTO además del resultado. Un escenario sin su supuesto es
    un número del que nadie puede decir de dónde salió, y en tres meses —cuando
    haya que explicar por qué se presupuestó eso— no habrá forma de reconstruirlo.
    """

    __tablename__ = "erp_escenarios"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "anio", "nombre", name="uq_erp_escenario"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"),
                           nullable=False, index=True)
    nombre = sa.Column(sa.String(120), nullable=False)
    descripcion = sa.Column(sa.Text)
    anio = sa.Column(sa.Integer, nullable=False)

    # El supuesto, en puntos porcentuales sobre el año base.
    supuesto_crecimiento = sa.Column(sa.Numeric(8, 2), nullable=False, default=0)
    supuesto_inflacion_costos = sa.Column(sa.Numeric(8, 2), nullable=False, default=0)

    # La base real sobre la que se proyectó, congelada. Sin ella, el escenario
    # cambiaría solo al cambiar la contabilidad y dejaría de ser comparable con
    # lo que se decidió aquel día.
    base_ingresos = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    base_costos = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    base_gastos = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    base_desde = sa.Column(sa.Date)
    base_hasta = sa.Column(sa.Date)

    ingresos_proyectados = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    costos_proyectados = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    gastos_proyectados = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    utilidad_proyectada = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    ebitda_pct = sa.Column(sa.Numeric(8, 2), nullable=False, default=0)

    creado_por = sa.Column(sa.String(200))


class ERPInductor(Base, TimestampMixin):
    """El criterio con el que se reparte un costo indirecto.

    «El arriendo se reparte por metros cuadrados ocupados» es una decisión de
    negocio, no un detalle técnico: repartirlo por horas hombre haría que
    almacenamiento pareciera barato y transporte caro. Por eso se configura, se
    guarda quién lo definió, y el reparto queda trazado hasta el asiento.
    """

    __tablename__ = "erp_inductores"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "codigo", name="uq_erp_inductor"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"),
                           nullable=False, index=True)
    codigo = sa.Column(sa.String(30), nullable=False)
    actividad = sa.Column(sa.String(160), nullable=False)
    # «m² ocupado», «km recorrido», «horas hombre»…
    inductor = sa.Column(sa.String(160), nullable=False)
    unidad = sa.Column(sa.String(20), nullable=False, default="und")

    # La cuenta cuyo saldo se reparte. Sin ella el costeo sería un cálculo
    # aparte que nunca cuadra con la contabilidad.
    cuenta_origen_id = sa.Column(sa.Integer, sa.ForeignKey("erp_plan_cuentas.id"))

    # {"3": 1200, "5": 400} — cuántas unidades del inductor consumió cada centro
    # de costo. Es lo que decide el reparto.
    consumo_por_centro = sa.Column(JSONB, default=dict, nullable=False)

    activo = sa.Column(sa.Boolean, default=True, nullable=False)
    definido_por = sa.Column(sa.String(200))


class ERPDistribucionABC(Base, TimestampMixin):
    """Un reparto ya hecho, con su asiento.

    Queda registro porque un reparto MUEVE saldos entre centros de costo: si no
    se sabe cuál se aplicó, dos informes del mismo mes pueden diferir y no hay
    manera de saber cuál está bien. Y porque repetirlo sin darse cuenta duplica
    el costo en el centro que lo recibe.
    """

    __tablename__ = "erp_distribuciones_abc"
    __table_args__ = (
        sa.UniqueConstraint("empresa_id", "inductor_id", "periodo",
                            name="uq_erp_distribucion"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    empresa_id = sa.Column(sa.Integer, sa.ForeignKey("erp_empresas.id"),
                           nullable=False, index=True)
    inductor_id = sa.Column(sa.Integer, sa.ForeignKey("erp_inductores.id"),
                            nullable=False)
    periodo = sa.Column(sa.String(7), nullable=False)   # AAAA-MM
    monto_distribuido = sa.Column(sa.Numeric(18, 2), nullable=False, default=0)
    # [{"centro_costo_id": 3, "unidades": 1200, "monto": 480000}, …]
    detalle = sa.Column(JSONB, default=list, nullable=False)
    comprobante_id = sa.Column(sa.Integer, sa.ForeignKey("erp_comprobantes.id"))
    ejecutado_por = sa.Column(sa.String(200))
