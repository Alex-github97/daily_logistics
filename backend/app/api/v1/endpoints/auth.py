from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
from app.core.database import get_db, get_db_plataforma
from app.core.tenant import codigo_valido, nombre_esquema
from app.core.acceso_modulos import modulos_de
from app.infrastructure.models.plataforma import PlataformaCliente
from app.core.security import verify_password, create_access_token, create_refresh_token, hash_password, decode_token
from app.core.dependencies import get_current_user, require_admin
from app.infrastructure.repositories.usuario_repository import UsuarioRepository
from app.infrastructure.models.usuario import Usuario, RolUsuario
from app.application.schemas.usuario import (
    LoginRequest, TokenResponse, UsuarioCreate, UsuarioResponse, ChangePasswordRequest
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])


class ClientePublico(BaseModel):
    """Lo que se puede saber de un cliente antes de autenticarse.

    Solo lo necesario para pintar su portal. Nada que sirva para deducir qué
    otros clientes existen.
    """
    model_config = ConfigDict(from_attributes=True)
    codigo: str
    nombre: str
    logo_url: Optional[str] = None
    color: Optional[str] = None


@router.get("/clientes/{codigo}", response_model=ClientePublico)
async def resolver_cliente(codigo: str, db: AsyncSession = Depends(get_db_plataforma)):
    """Paso previo al login: valida el cliente y devuelve su identidad visual.

    No hay endpoint que liste los clientes: quien entra debe saber su código,
    de modo que desde fuera no se pueda averiguar quién más usa la plataforma.
    """
    codigo = (codigo or "").strip().lower()
    if not codigo_valido(codigo):
        raise HTTPException(404, "No existe un cliente con ese código")
    r = await db.execute(
        select(PlataformaCliente).where(PlataformaCliente.codigo == codigo)
    )
    cliente = r.scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "No existe un cliente con ese código")
    if not cliente.activo:
        raise HTTPException(403, f"El acceso de {cliente.nombre} está suspendido.")
    return ClientePublico.model_validate(cliente)


async def _cliente_de_la_peticion(
    x_cliente: Optional[str], db: AsyncSession,
) -> PlataformaCliente:
    codigo = (x_cliente or "").strip().lower()
    if not codigo:
        raise HTTPException(400, "Indique el cliente antes de iniciar sesión")
    if not codigo_valido(codigo):
        raise HTTPException(404, "No existe un cliente con ese código")
    r = await db.execute(
        select(PlataformaCliente).where(PlataformaCliente.codigo == codigo)
    )
    cliente = r.scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "No existe un cliente con ese código")
    if not cliente.activo:
        raise HTTPException(403, f"El acceso de {cliente.nombre} está suspendido.")
    return cliente


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    x_cliente: Optional[str] = Header(None, alias="X-Cliente"),
    db: AsyncSession = Depends(get_db),
    db_plataforma: AsyncSession = Depends(get_db_plataforma),
):
    # El usuario se busca dentro del esquema del cliente: dos empresas pueden
    # tener un "admin" cada una y son personas distintas.
    cliente = await _cliente_de_la_peticion(x_cliente, db_plataforma)

    # El esquema se toma del registro, que es la única fuente válida: deducirlo
    # del código mandaría al cliente que ya existía —y vive en "public"— a un
    # esquema que no es el suyo.
    await db.execute(text(f'SET search_path TO "{cliente.esquema}"'))

    repo = UsuarioRepository(db)
    user = await repo.get_by_username(data.username)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if user.bloqueado:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario bloqueado")

    user.ultimo_login = datetime.now(timezone.utc)
    user.intentos_fallidos = 0
    await db.flush()

    # ¿Es usuario del portal de un depositante (cliente del 3PL)?
    from app.infrastructure.models.wms import WMSDepositante, WMSDepositanteUsuario
    vinculo = (await db.execute(select(WMSDepositanteUsuario, WMSDepositante).join(
        WMSDepositante, WMSDepositante.id == WMSDepositanteUsuario.depositante_id).where(
        WMSDepositanteUsuario.usuario_id == user.id))).first()
    portal = {"depositante_id": vinculo[1].id, "nombre": vinculo[1].nombre} if vinculo else None

    return TokenResponse(
        access_token=create_access_token(
            user.id, cliente=cliente.codigo, esquema=cliente.esquema,
            usuario=user.username, depositante=portal["depositante_id"] if portal else None),
        portal=portal,
        refresh_token=create_refresh_token(
            user.id, cliente=cliente.codigo, esquema=cliente.esquema),
        user=UsuarioResponse.model_validate(user),
        es_operador=bool(cliente.es_operador),
        modulos=sorted(await modulos_de(cliente.codigo)),
    )


async def require_operador(
    request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    usuario: Usuario = Depends(require_admin),
) -> Usuario:
    """Exige ser administrador DE LA EMPRESA QUE OPERA la plataforma.

    No basta el rol ADMINISTRADOR: ese lo tiene el administrador de cada
    cliente dentro de su esquema, así que con él solo, el administrador de una
    empresa podía listar y suspender a las demás.

    La empresa se toma del token, que la lleva firmada, y la marca de operador
    del registro, que vive fuera de los esquemas.
    """
    auth = request.headers.get("authorization") or ""
    codigo = decode_token(auth[7:]).get("cli") if auth.lower().startswith("bearer ") else None
    if not codigo:
        raise HTTPException(403, "La sesión no indica a qué empresa pertenece")
    r = await db.execute(
        select(PlataformaCliente).where(PlataformaCliente.codigo == codigo)
    )
    cliente = r.scalar_one_or_none()
    if not cliente or not cliente.es_operador:
        raise HTTPException(
            403,
            "Solo quien opera la plataforma puede administrar empresas.",
        )
    return usuario


class ClienteAdmin(ClientePublico):
    """La ficha completa, solo para quien administra la plataforma."""
    id: int
    esquema: str
    nit: Optional[str] = None
    activo: bool
    es_operador: bool = False


class ClienteCrear(BaseModel):
    codigo: str
    nombre: str
    nit: Optional[str] = None
    logo_url: Optional[str] = None
    color: Optional[str] = None


@router.get("/plataforma/clientes", response_model=List[ClienteAdmin])
async def listar_clientes(
    db: AsyncSession = Depends(get_db_plataforma),
    _: Usuario = Depends(require_operador),
):
    r = await db.execute(select(PlataformaCliente).order_by(PlataformaCliente.nombre))
    return list(r.scalars().all())


@router.post("/plataforma/clientes", response_model=ClienteAdmin, status_code=201)
async def crear_cliente(
    data: ClienteCrear,
    db: AsyncSession = Depends(get_db_plataforma),
    _: Usuario = Depends(require_operador),
):
    """Da de alta una empresa y le crea su esquema con todas las tablas.

    El alta no es solo una fila: hay que levantarle el juego completo de tablas,
    porque cada cliente tiene las suyas.
    """
    codigo = (data.codigo or "").strip().lower()
    if not codigo_valido(codigo):
        raise HTTPException(
            400,
            "El código debe empezar por letra y llevar solo minúsculas, dígitos o guion bajo: "
            "termina siendo el nombre del esquema donde viven sus datos.",
        )
    existe = await db.execute(
        select(PlataformaCliente).where(PlataformaCliente.codigo == codigo)
    )
    if existe.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe una empresa con el código «{codigo}»")

    cliente = PlataformaCliente(
        codigo=codigo, nombre=data.nombre.strip(), esquema=nombre_esquema(codigo),
        nit=data.nit, logo_url=data.logo_url, color=data.color, activo=True,
    )
    db.add(cliente)
    await db.flush()

    # Se crea acá y no en el próximo arranque: el cliente debe poder entrar
    # apenas se le da de alta.
    from app.main import _migrar_esquema
    await _migrar_esquema(cliente.esquema)

    await db.commit(); await db.refresh(cliente)
    return cliente


@router.put("/plataforma/clientes/{cliente_id}", response_model=ClienteAdmin)
async def actualizar_cliente(
    cliente_id: int,
    data: ClienteCrear,
    db: AsyncSession = Depends(get_db_plataforma),
    _: Usuario = Depends(require_operador),
):
    cliente = await db.get(PlataformaCliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Empresa no encontrada")
    # El código no se toca: es el nombre del esquema, y cambiarlo dejaría sus
    # tablas huérfanas.
    cliente.nombre = data.nombre.strip()
    cliente.nit = data.nit
    cliente.logo_url = data.logo_url
    cliente.color = data.color
    await db.commit(); await db.refresh(cliente)
    return cliente


@router.put("/plataforma/clientes/{cliente_id}/estado", response_model=ClienteAdmin)
async def cambiar_estado_cliente(
    cliente_id: int,
    activo: bool,
    db: AsyncSession = Depends(get_db_plataforma),
    _: Usuario = Depends(require_operador),
):
    """Suspende o reactiva el acceso, sin tocar los datos.

    No hay borrado: eliminar una empresa sería eliminar su esquema entero con
    todo su historial, y eso no puede depender de un clic.
    """
    cliente = await db.get(PlataformaCliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Empresa no encontrada")
    cliente.activo = activo
    cliente.suspendido_desde = None if activo else datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit(); await db.refresh(cliente)
    return cliente


@router.get("/me", response_model=UsuarioResponse)
async def get_me(current_user: Usuario = Depends(get_current_user)):
    return UsuarioResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.password_actual, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    current_user.hashed_password = hash_password(data.password_nuevo)
    await db.flush()
    return {"message": "Contraseña actualizada exitosamente"}
