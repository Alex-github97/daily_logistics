"""Seed inicial: usuarios, ubicaciones, proveedores, códigos de daño."""
import asyncio
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.security import hash_password
from app.infrastructure.models import *

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    from app.core.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Usuarios
        admin = Usuario(
            nombre="Administrador", apellido="Sistema",
            email="admin@empresa.com", username="admin",
            hashed_password=hash_password("Admin@2025"),
            rol=RolUsuario.ADMINISTRADOR, cargo="Administrador del Sistema",
        )
        supervisor = Usuario(
            nombre="Supervisor", apellido="Logístico",
            email="supervisor@empresa.com", username="supervisor",
            hashed_password=hash_password("Super@2025"),
            rol=RolUsuario.SUPERVISOR_LOGISTICO, cargo="Supervisor Logístico",
        )
        operador = Usuario(
            nombre="Operador", apellido="Bodega",
            email="operador@empresa.com", username="operador",
            hashed_password=hash_password("Oper@2025"),
            rol=RolUsuario.OPERADOR_BODEGA, cargo="Operador de Bodega",
        )
        db.add_all([admin, supervisor, operador])

        # Ubicaciones
        ubicaciones = [
            Ubicacion(codigo="BOD-001", nombre="Bodega Principal Bogotá", tipo=TipoUbicacion.BODEGA, ciudad="Bogotá", capacidad_estibas=500),
            Ubicacion(codigo="BOD-002", nombre="Bodega Medellín", tipo=TipoUbicacion.BODEGA, ciudad="Medellín", capacidad_estibas=300),
            Ubicacion(codigo="PLT-001", nombre="Planta Norte", tipo=TipoUbicacion.PLANTA, ciudad="Bogotá", capacidad_estibas=200),
            Ubicacion(codigo="PAT-001", nombre="Patio Externo Bogotá", tipo=TipoUbicacion.PATIO, ciudad="Bogotá", capacidad_estibas=1000),
            Ubicacion(codigo="DIS-001", nombre="Disposición Final", tipo=TipoUbicacion.DISPOSICION_FINAL, ciudad="Bogotá", es_disposicion_final=True),
            Ubicacion(codigo="CLI-001", nombre="Cliente Mondelēz", tipo=TipoUbicacion.CLIENTE, ciudad="Bogotá"),
            Ubicacion(codigo="CLI-002", nombre="Cliente Bavaria", tipo=TipoUbicacion.CLIENTE, ciudad="Bogotá"),
        ]
        db.add_all(ubicaciones)

        # Transportadora
        transportadora = Transportadora(
            nit="900123456-1", razon_social="Transportes Nacionales S.A.S.",
            nombre_comercial="TransNal", ciudad="Bogotá",
        )
        db.add(transportadora)

        # Códigos de daño
        codigos_dano = [
            CodigoDano(codigo="D001", descripcion="Tabla rota", categoria="Daño Estructural", costo_reparacion_promedio=50000),
            CodigoDano(codigo="D002", descripcion="Taco faltante", categoria="Daño Estructural", costo_reparacion_promedio=30000),
            CodigoDano(codigo="D003", descripcion="Daño por montacargas", categoria="Daño Operativo", costo_reparacion_promedio=120000),
            CodigoDano(codigo="D004", descripcion="Daño por transporte", categoria="Daño Operativo", costo_reparacion_promedio=80000),
            CodigoDano(codigo="D005", descripcion="Humedad", categoria="Daño Ambiental", costo_reparacion_promedio=60000),
            CodigoDano(codigo="D006", descripcion="Contaminación", categoria="Daño Ambiental", costo_reparacion_promedio=40000),
            CodigoDano(codigo="D007", descripcion="Robo", categoria="Pérdida", costo_reparacion_promedio=0),
            CodigoDano(codigo="D008", descripcion="Incendio", categoria="Pérdida Total", costo_reparacion_promedio=0),
            CodigoDano(codigo="D009", descripcion="Deformación por carga excesiva", categoria="Daño Operativo", costo_reparacion_promedio=90000),
            CodigoDano(codigo="D010", descripcion="Astillamiento", categoria="Daño Estructural", costo_reparacion_promedio=45000),
        ]
        db.add_all(codigos_dano)

        await db.commit()
        print("✓ Seed completado exitosamente")
        print("  Usuarios: admin / supervisor / operador")
        print("  Contraseñas: Admin@2025 / Super@2025 / Oper@2025")


if __name__ == "__main__":
    asyncio.run(seed())
