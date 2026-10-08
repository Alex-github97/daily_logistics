import qrcode
import io
import base64
from typing import Optional, List
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.repositories.estiba_repository import EstibaRepository
from app.infrastructure.models.estiba import Estiba, EstadoEstiba
from app.infrastructure.models.usuario import Usuario
from app.application.schemas.estiba import EstibaCreate, EstibaUpdate, EstibaListResponse
from fastapi import HTTPException, status


class EstibaService:
    def __init__(self, db: AsyncSession):
        self.repo = EstibaRepository(db)

    async def crear_estiba(self, data: EstibaCreate, usuario: Usuario) -> Estiba:
        existing = await self.repo.get_by_codigo(data.codigo_interno)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una estiba con el código {data.codigo_interno}",
            )

        qr_data = f"ESTIBA:{data.codigo_interno}:CI"
        qr_code = self._generate_qr_base64(qr_data)

        estiba = Estiba(
            codigo_interno=data.codigo_interno,
            codigo_qr=qr_code,
            tipo=data.tipo,
            material=data.material,
            largo_cm=data.largo_cm,
            ancho_cm=data.ancho_cm,
            alto_cm=data.alto_cm,
            peso_kg=data.peso_kg,
            capacidad_carga_kg=data.capacidad_carga_kg,
            tipo_propietario=data.tipo_propietario,
            proveedor_id=data.proveedor_id,
            contrato_id=data.contrato_id,
            fecha_ingreso=data.fecha_ingreso or date.today(),
            fecha_fabricacion=data.fecha_fabricacion,
            vida_util_anos=data.vida_util_anos,
            valor_compra=data.valor_compra,
            valor_actual=data.valor_actual or data.valor_compra,
            moneda=data.moneda,
            observaciones=data.observaciones,
            estado=EstadoEstiba.EN_INVENTARIO,
            ubicacion_actual_id=data.ubicacion_inicial_id,
        )
        return await self.repo.create(estiba)

    async def obtener_estiba(self, estiba_id: int) -> Estiba:
        estiba = await self.repo.get_with_relations(estiba_id)
        if not estiba:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estiba no encontrada")
        return estiba

    async def buscar_por_codigo(self, codigo: str) -> Estiba:
        # Los QR impresos contienen "ESTIBA:{codigo_interno}:CI" — extraer el código interno
        search_code = codigo
        if codigo.startswith('ESTIBA:') and codigo.endswith(':CI'):
            search_code = codigo[len('ESTIBA:'):-len(':CI')]

        estiba = await self.repo.get_by_codigo(search_code)
        if not estiba:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Estiba '{codigo}' no encontrada")
        return estiba

    async def listar_estibas(
        self, page: int = 1, page_size: int = 50,
        estado: Optional[str] = None,
        tipo_propietario: Optional[str] = None,
        ubicacion_id: Optional[int] = None,
        proveedor_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> EstibaListResponse:
        skip = (page - 1) * page_size
        items, total = await self.repo.get_filtered(
            skip=skip, limit=page_size,
            estado=estado, tipo_propietario=tipo_propietario,
            ubicacion_id=ubicacion_id, proveedor_id=proveedor_id,
            search=search,
        )
        pages = (total + page_size - 1) // page_size
        return EstibaListResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)

    async def actualizar_estiba(self, estiba_id: int, data: EstibaUpdate) -> Estiba:
        estiba = await self.repo.get_by_id(estiba_id)
        if not estiba:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estiba no encontrada")
        update_data = data.model_dump(exclude_unset=True)
        return await self.repo.update(estiba, update_data)

    async def dar_de_baja(self, estiba_id: int, motivo: str, usuario: Usuario) -> Estiba:
        estiba = await self.repo.get_by_id(estiba_id)
        if not estiba:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estiba no encontrada")
        estiba.estado = EstadoEstiba.BAJA
        estiba.observaciones = f"BAJA: {motivo}"
        await self.repo.db.flush()
        return estiba

    async def eliminar_estiba(self, estiba_id: int) -> None:
        estiba = await self.repo.get_by_id(estiba_id)
        if not estiba:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estiba no encontrada")
        await self.repo.soft_delete(estiba)

    async def get_kpis(self) -> dict:
        return await self.repo.get_kpis()

    def _generate_qr_base64(self, data: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
