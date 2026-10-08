import re

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy import MetaData, event, text
from app.core.config import settings
from app.core.tenant import ESQUEMA_PLATAFORMA, esquema_actual

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

def _url_sin_cache_de_planes(url: str) -> str:
    """Agrega `prepared_statement_cache_size=0` a la URL de conexión.

    El dialecto de asyncpg lee ese ajuste de la URL y no de `create_engine`:
    pasarlo como argumento tumba el arranque con `Invalid argument(s)`.
    """
    if "prepared_statement_cache_size" in url:
        return url
    return url + ("&" if "?" in url else "?") + "prepared_statement_cache_size=0"


engine = create_async_engine(
    _url_sin_cache_de_planes(settings.DATABASE_URL),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    # ── Sin caché de planes: es la otra cara del `search_path` ──
    #
    # asyncpg prepara cada consulta y guarda su plan en la conexión, con el SQL
    # como llave. Pero acá el mismo SQL no siempre habla de la misma tabla: al
    # cambiar de cliente cambia el `search_path`, y `SELECT ... FROM eam_activo`
    # deja de referirse a la tabla que el plan tenía resuelta.
    #
    # Lo que se veía en producción era un 500 esporádico —
    # `InvalidCachedStatementError`— en pantallas que consultan catálogos, y
    # nunca en local, donde hay un solo cliente y el esquema no rota. Se caía
    # justo después de que la conexión hubiera atendido a otra empresa.
    #
    # Apagar la caché cuesta un poco de tiempo por consulta y es el precio de
    # tener un esquema por cliente. La alternativa —adivinar cuándo invalidar—
    # es la misma clase de suposición que ya había fallado. El ajuste va en la
    # URL, arriba: como argumento de `create_async_engine` no lo acepta.
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    metadata = metadata


# ══════════════════════════════════════════════════════════════════════════════
# EL `search_path` SE REPONE EN CADA TRANSACCIÓN, NO UNA VEZ POR PETICIÓN
# ══════════════════════════════════════════════════════════════════════════════
#
# `SET search_path` vive en la CONEXIÓN, no en la sesión. Al hacer `commit()`,
# SQLAlchemy devuelve la conexión al pool; la siguiente operación de la misma
# petición —un `refresh()` después de guardar, por ejemplo— toma otra conexión,
# que puede traer el esquema que le dejó puesto la petición anterior.
#
# Eso producía dos cosas, y las dos se vieron en producción:
#
#   1. `Could not refresh instance`: el INSERT quedaba hecho pero la respuesta
#      fallaba con 500, porque el SELECT del refresh buscaba la fila en el
#      esquema equivocado. El cliente veía un error y reintentaba, y terminaba
#      con registros duplicados.
#
#   2. Lo grave: una consulta después del commit podía correr contra el esquema
#      de OTRO cliente. Casi siempre no encuentra nada y falla, pero el
#      aislamiento entre empresas —que es la promesa central de la plataforma—
#      dependía de que la conexión no rotara en mitad de la petición.
#
# Fijarlo al abrir la sesión no alcanzaba: hay que reponerlo cada vez que se
# empieza una transacción, que es exactamente cuando se toma una conexión. El
# evento `after_begin` corre sobre la conexión real y con la sesión ya asociada,
# así que es el punto donde la garantía se puede sostener.
@event.listens_for(Session, "after_begin")
def _fijar_esquema(session, transaction, connection) -> None:
    esquema = session.info.get("esquema")
    if not esquema:
        return   # sesiones internas (migraciones, arranque) manejan lo suyo
    # `search_path` no admite parámetros: hay que interpolar. El código del
    # cliente se valida al crearlo y al resolverlo, y acá se vuelve a acotar
    # para que un valor inesperado no llegue nunca al SQL.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", esquema):
        raise ValueError(f"Nombre de esquema no admitido: {esquema!r}")
    connection.exec_driver_sql(f'SET search_path TO "{esquema}"')


async def get_db() -> AsyncSession:
    """Sesión ya apuntando al esquema del cliente en curso.

    El `search_path` se fija acá y no en cada consulta: es lo que hace que los
    módulos no tengan que filtrar por cliente y que no puedan equivocarse.
    """
    # El esquema se declara en la sesión y el evento `after_begin` lo repone en
    # cada transacción. Fijarlo una sola vez acá no bastaba: tras un `commit()`
    # la conexión vuelve al pool y la siguiente puede traer el esquema de otro
    # cliente. Solo su esquema: con public detrás, una tabla que falte en el
    # cliente se resolvería contra la de otro.
    async with AsyncSessionLocal(
            info={"esquema": esquema_actual() or ESQUEMA_PLATAFORMA}) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_plataforma() -> AsyncSession:
    """Sesión contra el registro de clientes, sin inquilino.

    La usa el paso previo al login, cuando todavía no se sabe a qué cliente se
    entra.
    """
    async with AsyncSessionLocal(info={"esquema": ESQUEMA_PLATAFORMA}) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
