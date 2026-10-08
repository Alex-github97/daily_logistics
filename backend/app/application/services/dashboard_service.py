from datetime import date, timedelta
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from app.infrastructure.models.estiba import Estiba, EstadoEstiba, TipoPropietario
from app.infrastructure.models.movimiento import Movimiento, TipoMovimiento
from app.infrastructure.models.alerta import Alerta
from app.infrastructure.models.manifiesto import Manifiesto, EstadoManifiesto
from app.infrastructure.models.dano import EventoDano, CodigoDano
from app.infrastructure.models.ubicacion import Ubicacion
from app.infrastructure.models.mantenimiento import MantenimientoEstiba
from app.application.schemas.dashboard import (
    DashboardResponse, KPIResumen, MovimientoTendencia,
    DanoEstadistica, UbicacionOcupacion, AlertaResumen,
    EdadDistribucion, CostoMensual, RetornoMensual, RetornoData,
)
from typing import Optional


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(self) -> DashboardResponse:
        kpis = await self._get_kpis()
        tendencia = await self._get_tendencia_movimientos(dias=30)
        top_danos = await self._get_top_danos()
        ocupacion = await self._get_ocupacion_ubicaciones()
        alertas = await self._get_alertas_recientes()
        movimientos_recientes = await self._get_movimientos_recientes()
        edad_distribucion = await self._get_edad_distribucion()
        costos_por_mes = await self._get_costos_por_mes()
        kpis.tiempo_promedio_retorno_dias = await self._get_promedio_retorno()

        return DashboardResponse(
            kpis=kpis,
            tendencia_movimientos=tendencia,
            top_danos=top_danos,
            ocupacion_ubicaciones=ocupacion,
            alertas_recientes=alertas,
            movimientos_recientes=movimientos_recientes,
            edad_distribucion=edad_distribucion,
            costos_por_mes=costos_por_mes,
        )

    async def get_retorno_data(self, bodega_id: Optional[int] = None) -> RetornoData:
        avg_dias = await self._get_promedio_retorno(bodega_id)
        por_mes = await self._get_retorno_por_mes(bodega_id)
        return RetornoData(tiempo_promedio_dias=avg_dias, retorno_por_mes=por_mes)

    def _retorno_lateral(self, bodega_id: Optional[int]) -> tuple:
        bodega_clause = "" if bodega_id is None else "AND c_data.bodega_id = :bodega_id"
        params: Dict[str, Any] = {} if bodega_id is None else {"bodega_id": bodega_id}
        fragment = f"""
            FROM movimientos r
            JOIN LATERAL (
                SELECT c.fecha_movimiento AS fecha_carga,
                       man.destino_id    AS bodega_id
                FROM movimientos c
                LEFT JOIN manifiestos man ON c.manifiesto_id = man.id
                WHERE c.estiba_id = r.estiba_id
                    AND c.tipo = 'CARGA'
                    AND c.fecha_movimiento < r.fecha_movimiento
                ORDER BY c.fecha_movimiento DESC
                LIMIT 1
            ) c_data ON true
            WHERE r.tipo = 'RETORNO'
                AND r.fecha_movimiento >= NOW() - INTERVAL '12 months'
                {bodega_clause}
        """
        return fragment, params

    async def _get_promedio_retorno(self, bodega_id: Optional[int] = None) -> float:
        lateral, params = self._retorno_lateral(bodega_id)
        result = await self.db.execute(
            text(f"""
                SELECT COALESCE(
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (r.fecha_movimiento - c_data.fecha_carga)) / 86400.0
                    )::numeric, 1),
                    0
                ) AS promedio_dias
                {lateral}
            """),
            params,
        )
        return float(result.scalar_one() or 0.0)

    async def _get_retorno_por_mes(self, bodega_id: Optional[int] = None) -> List[RetornoMensual]:
        lateral, params = self._retorno_lateral(bodega_id)
        result = await self.db.execute(
            text(f"""
                SELECT
                    to_char(r.fecha_movimiento AT TIME ZONE 'America/Bogota', 'YYYY-MM') AS mes,
                    ROUND(AVG(
                        EXTRACT(EPOCH FROM (r.fecha_movimiento - c_data.fecha_carga)) / 86400.0
                    )::numeric, 1) AS promedio_dias,
                    COUNT(*) AS cantidad
                {lateral}
                GROUP BY to_char(r.fecha_movimiento AT TIME ZONE 'America/Bogota', 'YYYY-MM')
                ORDER BY mes
            """),
            params,
        )
        rows = result.all()
        return [
            RetornoMensual(mes=r.mes, promedio_dias=float(r.promedio_dias), cantidad_retornos=int(r.cantidad))
            for r in rows
        ]

    async def _get_kpis(self) -> KPIResumen:
        estado_counts = await self.db.execute(
            select(Estiba.estado, func.count(Estiba.id))
            .where(Estiba.activo == True)
            .group_by(Estiba.estado)
        )
        counts = {row[0]: row[1] for row in estado_counts.all()}

        propietario_counts = await self.db.execute(
            select(Estiba.tipo_propietario, func.count(Estiba.id))
            .where(Estiba.activo == True)
            .group_by(Estiba.tipo_propietario)
        )
        prop_counts = {row[0]: row[1] for row in propietario_counts.all()}

        alertas_activas = await self.db.execute(
            select(func.count(Alerta.id)).where(Alerta.resuelta == False)
        )

        hoy = date.today()
        movimientos_hoy = await self.db.execute(
            select(func.count(Movimiento.id)).where(
                func.date(Movimiento.fecha_movimiento) == hoy
            )
        )

        manifiestos_activos = await self.db.execute(
            select(func.count(Manifiesto.id)).where(
                Manifiesto.estado.in_([EstadoManifiesto.EN_TRANSITO, EstadoManifiesto.EN_CARGUE])
            )
        )

        # Edad promedio en meses
        fechas_result = await self.db.execute(
            select(Estiba.fecha_ingreso).where(
                Estiba.activo == True, Estiba.fecha_ingreso.isnot(None)
            )
        )
        fechas = fechas_result.scalars().all()
        ages_months = [(hoy - f).days / 30.44 for f in fechas if f]
        edad_promedio = round(sum(ages_months) / len(ages_months), 1) if ages_months else 0.0

        # Total costos acumulados de mantenimiento
        total_costos_result = await self.db.execute(
            select(func.coalesce(func.sum(MantenimientoEstiba.costo), 0.0))
        )
        total_costos = float(total_costos_result.scalar_one())

        # Valor total de estibas PERDIDAS (para cuantificar pérdidas monetarias)
        valor_perdidas_result = await self.db.execute(
            select(func.coalesce(func.sum(Estiba.valor_actual), 0.0))
            .where(Estiba.estado == EstadoEstiba.PERDIDA)
        )
        valor_perdidas = float(valor_perdidas_result.scalar_one())

        total = sum(counts.values())
        return KPIResumen(
            total_estibas=total,
            disponibles=counts.get(EstadoEstiba.DISPONIBLE, 0) + counts.get(EstadoEstiba.EN_INVENTARIO, 0),
            en_transito=counts.get(EstadoEstiba.EN_TRANSITO, 0),
            en_cliente=counts.get(EstadoEstiba.EN_CLIENTE, 0),
            pendiente_retorno=counts.get(EstadoEstiba.PENDIENTE_RETORNO, 0),
            danadas=counts.get(EstadoEstiba.DANADA, 0),
            en_reparacion=counts.get(EstadoEstiba.EN_REPARACION, 0),
            faltantes=counts.get(EstadoEstiba.FALTANTE, 0),
            perdidas=counts.get(EstadoEstiba.PERDIDA, 0),
            valor_perdidas=valor_perdidas,
            propias=prop_counts.get(TipoPropietario.PROPIA, 0),
            alquiladas=prop_counts.get(TipoPropietario.ALQUILADA, 0),
            alertas_activas=alertas_activas.scalar_one(),
            movimientos_hoy=movimientos_hoy.scalar_one(),
            manifiestos_activos=manifiestos_activos.scalar_one(),
            edad_promedio_meses=edad_promedio,
            total_costos_acumulados=total_costos,
        )

    async def _get_edad_distribucion(self) -> List[EdadDistribucion]:
        fechas_result = await self.db.execute(
            select(Estiba.fecha_ingreso).where(
                Estiba.activo == True, Estiba.fecha_ingreso.isnot(None)
            )
        )
        fechas = fechas_result.scalars().all()
        hoy = date.today()

        buckets: Dict[str, int] = {"0-6m": 0, "6-12m": 0, "12-24m": 0, "24-36m": 0, "36m+": 0}
        for f in fechas:
            m = (hoy - f).days / 30.44
            if m < 6:
                buckets["0-6m"] += 1
            elif m < 12:
                buckets["6-12m"] += 1
            elif m < 24:
                buckets["12-24m"] += 1
            elif m < 36:
                buckets["24-36m"] += 1
            else:
                buckets["36m+"] += 1

        total = sum(buckets.values()) or 1
        return [
            EdadDistribucion(rango=rango, cantidad=cant, porcentaje=round(cant / total * 100, 1))
            for rango, cant in buckets.items()
        ]

    async def _get_costos_por_mes(self) -> List[CostoMensual]:
        hace_12_meses = date.today().replace(day=1) - timedelta(days=365)
        result = await self.db.execute(
            text("""
                SELECT
                    to_char(fecha, 'YYYY-MM') AS mes,
                    SUM(costo)                AS costo_total,
                    COUNT(id)                 AS cantidad
                FROM mantenimientos_estiba
                WHERE fecha >= :desde
                GROUP BY to_char(fecha, 'YYYY-MM')
                ORDER BY to_char(fecha, 'YYYY-MM')
            """),
            {"desde": hace_12_meses},
        )
        rows = result.all()
        return [
            CostoMensual(mes=row.mes, costo_total=float(row.costo_total), cantidad_mantenimientos=int(row.cantidad))
            for row in rows
        ]

    async def _get_tendencia_movimientos(self, dias: int = 30) -> List[MovimientoTendencia]:
        resultado = []
        hoy = date.today()
        for i in range(dias - 1, -1, -1):
            dia = hoy - timedelta(days=i)
            tipos_count = await self.db.execute(
                select(Movimiento.tipo, func.count(Movimiento.id))
                .where(func.date(Movimiento.fecha_movimiento) == dia)
                .group_by(Movimiento.tipo)
            )
            counts = {row[0]: row[1] for row in tipos_count.all()}
            cargas = counts.get(TipoMovimiento.CARGA, 0)
            descargas = counts.get(TipoMovimiento.DESCARGA, 0)
            transferencias = counts.get(TipoMovimiento.TRANSFERENCIA, 0)
            resultado.append(MovimientoTendencia(
                fecha=dia, cargas=cargas, descargas=descargas,
                transferencias=transferencias, total=cargas + descargas + transferencias
            ))
        return resultado

    async def _get_top_danos(self) -> List[DanoEstadistica]:
        result = await self.db.execute(
            select(CodigoDano.codigo, CodigoDano.descripcion, func.count(EventoDano.id).label("cantidad"))
            .join(EventoDano, EventoDano.codigo_dano_id == CodigoDano.id)
            .group_by(CodigoDano.id, CodigoDano.codigo, CodigoDano.descripcion)
            .order_by(func.count(EventoDano.id).desc())
            .limit(10)
        )
        rows = result.all()
        total = sum(r.cantidad for r in rows) or 1
        return [
            DanoEstadistica(
                codigo=r.codigo, descripcion=r.descripcion, cantidad=r.cantidad,
                porcentaje=round(r.cantidad / total * 100, 1),
            )
            for r in rows
        ]

    async def _get_ocupacion_ubicaciones(self) -> List[UbicacionOcupacion]:
        result = await self.db.execute(
            select(Ubicacion.id, Ubicacion.nombre, Ubicacion.tipo, Ubicacion.capacidad_estibas,
                   func.count(Estiba.id).label("total"))
            .outerjoin(Estiba, and_(Estiba.ubicacion_actual_id == Ubicacion.id, Estiba.activo == True))
            .where(Ubicacion.activo == True)
            .group_by(Ubicacion.id, Ubicacion.nombre, Ubicacion.tipo, Ubicacion.capacidad_estibas)
            .order_by(func.count(Estiba.id).desc())
            .limit(10)
        )
        rows = result.all()
        return [
            UbicacionOcupacion(
                ubicacion_id=r.id, nombre=r.nombre,
                tipo=r.tipo.value if hasattr(r.tipo, "value") else str(r.tipo),
                total_estibas=r.total, capacidad=r.capacidad_estibas,
                porcentaje_ocupacion=round(r.total / r.capacidad_estibas * 100, 1) if r.capacidad_estibas else None,
            )
            for r in rows
        ]

    async def _get_alertas_recientes(self) -> List[AlertaResumen]:
        result = await self.db.execute(
            select(Alerta).where(Alerta.resuelta == False)
            .order_by(Alerta.created_at.desc()).limit(5)
        )
        alertas = result.scalars().all()
        return [
            AlertaResumen(id=a.id, tipo=a.tipo.value, nivel=a.nivel.value, titulo=a.titulo, fecha=a.created_at.isoformat())
            for a in alertas
        ]

    async def _get_movimientos_recientes(self) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(Movimiento).order_by(Movimiento.fecha_movimiento.desc()).limit(10)
        )
        movimientos = result.scalars().all()
        return [
            {"id": m.id, "tipo": m.tipo.value, "estiba_id": m.estiba_id,
             "fecha": m.fecha_movimiento.isoformat(), "usuario_id": m.usuario_id}
            for m in movimientos
        ]
