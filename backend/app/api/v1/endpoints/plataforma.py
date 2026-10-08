"""
Consola del operador: administración de las empresas y de su gente.

Esto NO es la administración que usa cada empresa sobre sí misma —esa vive en
`usuarios.py` y trabaja siempre dentro del esquema de quien está conectado—.
Acá el operador actúa *sobre otros esquemas*, que es un poder distinto y mucho
mayor, y por eso está en un módulo aparte, detrás de un permiso concreto y con
todo lo que hace registrado en la bitácora.

Regla que sostiene el diseño: la consola administra el **acceso**, no los datos.
Deja crear usuarios y devolver claves, que es lo que hace falta para dar de alta
y para rescatar a un cliente bloqueado; no deja leer sus estibas, sus activos ni
sus llantas.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import re
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import or_, select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db_plataforma
from app.core.security import decode_token, hash_password
from app.core.tenant import ESQUEMA_PLATAFORMA, codigo_valido
from app.infrastructure.models.plataforma import PlataformaCliente, PlataformaBitacora
from app.infrastructure.models.usuario import Usuario
from app.core.permisos_consola import Miembro, exigir
from app.core.permisos_perfil import PERMISOS_PERFIL, normalizar as normalizar_permisos

router = APIRouter(prefix="/plataforma", tags=["Consola del operador"])


# ─── Trabajar dentro del esquema de otra empresa ──────────────────────────────

@asynccontextmanager
async def _sesion_de(esquema: str):
    """Una sesión apuntando al esquema de la empresa indicada.

    `get_db` fija el esquema a partir del token, que es el de quien está
    conectado; acá hace falta lo contrario: el operador entra desde su propia
    empresa y necesita escribir en la de otra.

    El esquema se interpola porque `search_path` no admite parámetros, así que
    solo puede venir del registro —nunca de la petición— y aun así se valida.
    """
    if not esquema or not esquema.replace("_", "").isalnum():
        raise HTTPException(400, f"Esquema inválido: «{esquema}»")
    async with AsyncSessionLocal() as s:
        try:
            await s.execute(text(f'SET search_path TO "{esquema}"'))
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


def _clave_temporal() -> str:
    """Una clave de un solo uso, para entregar y cambiar.

    Se excluyen los caracteres que se confunden al dictarla por teléfono (O/0,
    l/1/I), porque estas claves se entregan a mano.
    """
    alfabeto = "".join(c for c in string.ascii_letters + string.digits if c not in "O0lI1")
    return "".join(secrets.choice(alfabeto) for _ in range(14))


async def _anotar(
    db: AsyncSession, request: Request, accion: str,
    empresa: Optional[str] = None, detalle: Optional[str] = None,
) -> None:
    """Deja constancia de lo que acaba de hacer el operador."""
    auth = request.headers.get("authorization") or ""
    datos = decode_token(auth[7:]) if auth.lower().startswith("bearer ") else {}
    db.add(PlataformaBitacora(
        fecha=datetime.utcnow(),
        actor=str(datos.get("usr") or datos.get("sub") or "?"),
        actor_empresa=str(datos.get("cli") or "?"),
        accion=accion,
        empresa_codigo=empresa,
        detalle=detalle,
    ))


async def _empresa(db: AsyncSession, cliente_id: int) -> PlataformaCliente:
    r = await db.execute(select(PlataformaCliente).where(PlataformaCliente.id == cliente_id))
    cliente = r.scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "No existe esa empresa")
    return cliente


# ─── Lo que se manda y se devuelve ────────────────────────────────────────────

class UsuarioDeEmpresa(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    apellido: str
    email: str
    username: str
    rol: str
    cargo: Optional[str] = None
    activo: bool
    bloqueado: Optional[bool] = None
    ultimo_login: Optional[datetime] = None


class UsuarioNuevo(BaseModel):
    nombre: str
    apellido: str = ""
    email: EmailStr
    username: str
    rol: str = "ADMINISTRADOR"
    cargo: Optional[str] = None


class UsuarioCambios(BaseModel):
    """Todo opcional: se manda solo lo que cambia."""
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[str] = None
    cargo: Optional[str] = None
    activo: Optional[bool] = None


class ClaveEntregada(BaseModel):
    """La clave se muestra una sola vez, al crearla o restablecerla.

    No se guarda en claro en ningún lado: si se pierde, se restablece otra.
    """
    username: str
    clave_temporal: str


class EmpresaEnLista(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    esquema: str
    nit: Optional[str] = None
    logo_url: Optional[str] = None
    color: Optional[str] = None
    activo: bool
    es_operador: bool = False
    suspendido_desde: Optional[datetime] = None
    # Cuántos usuarios tiene. Una empresa en cero no la puede usar nadie: es el
    # estado en el que quedaba toda empresa recién creada antes de esta consola.
    usuarios: int = 0
    usuarios_activos: int = 0


class AsientoBitacora(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha: datetime
    actor: str
    actor_empresa: str
    accion: str
    empresa_codigo: Optional[str] = None
    detalle: Optional[str] = None


# ─── Empresas ─────────────────────────────────────────────────────────────────

@router.get("/empresas", response_model=List[EmpresaEnLista])
async def listar_empresas(
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.ver")),
):
    """Las empresas, con cuánta gente tiene cada una.

    El conteo se pide esquema por esquema porque cada empresa tiene su propia
    tabla `usuarios`; son pocas empresas y la consola no se abre a cada rato.
    """
    r = await db.execute(select(PlataformaCliente).order_by(PlataformaCliente.nombre))
    empresas = list(r.scalars().all())

    salida: List[EmpresaEnLista] = []
    for e in empresas:
        total = activos = 0
        try:
            async with _sesion_de(e.esquema) as s:
                total = (await s.execute(text("SELECT count(*) FROM usuarios"))).scalar() or 0
                activos = (await s.execute(
                    text("SELECT count(*) FROM usuarios WHERE activo")
                )).scalar() or 0
        except Exception:
            # Un esquema a medio crear no debe tumbar la lista entera: se
            # muestra en cero, que es justo la señal de que algo le falta.
            pass
        ficha = EmpresaEnLista.model_validate(e)
        ficha.usuarios, ficha.usuarios_activos = total, activos
        salida.append(ficha)
    return salida


class EmpresaNueva(BaseModel):
    codigo: str
    nombre: str
    nit: Optional[str] = None
    logo_url: Optional[str] = None
    color: Optional[str] = None
    # El primer administrador va en el mismo paso a propósito: una empresa sin
    # usuarios no la puede usar nadie, y así no queda ninguna a medio dar de alta.
    admin_nombre: str = "Administrador"
    admin_apellido: str = ""
    admin_email: EmailStr
    admin_username: str = "admin"


class EmpresaCreada(BaseModel):
    empresa: EmpresaEnLista
    acceso: ClaveEntregada


@router.post("/empresas", response_model=EmpresaCreada, status_code=201)
async def crear_empresa(
    data: EmpresaNueva,
    request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.crear")),
):
    """Da de alta una empresa: su esquema, sus tablas y su administrador.

    Las tres cosas van juntas porque por separado no sirven de nada: hasta
    ahora el alta creaba el esquema y las 416 tablas pero ningún usuario, y la
    empresa quedaba inaccesible — había que sembrarle el administrador con SQL
    directo en el servidor.
    """
    codigo = (data.codigo or "").strip().lower()
    if not codigo_valido(codigo):
        raise HTTPException(
            400,
            "El código debe empezar por letra y llevar solo minúsculas, dígitos o "
            "guion bajo: termina siendo el nombre del esquema donde viven sus datos.",
        )
    ya = await db.execute(select(PlataformaCliente).where(PlataformaCliente.codigo == codigo))
    if ya.scalar_one_or_none():
        raise HTTPException(409, f"Ya existe una empresa con el código «{codigo}»")

    from app.core.tenant import nombre_esquema
    cliente = PlataformaCliente(
        codigo=codigo, nombre=data.nombre.strip(), esquema=nombre_esquema(codigo),
        nit=data.nit, logo_url=data.logo_url, color=data.color, activo=True,
    )
    db.add(cliente)
    await db.flush()

    # Se levantan acá y no en el próximo arranque: la empresa debe poder entrar
    # apenas se le da de alta.
    from app.main import _migrar_esquema
    await _migrar_esquema(cliente.esquema)

    clave = _clave_temporal()
    async with _sesion_de(cliente.esquema) as s:
        s.add(Usuario(
            nombre=data.admin_nombre.strip() or "Administrador",
            apellido=data.admin_apellido.strip(),
            email=str(data.admin_email),
            username=data.admin_username.strip().lower(),
            hashed_password=hash_password(clave),
            rol="ADMINISTRADOR",
            activo=True,
        ))

    await _anotar(db, request, "empresa.alta", codigo,
                  f"con administrador «{data.admin_username}»")
    await db.commit(); await db.refresh(cliente)

    ficha = EmpresaEnLista.model_validate(cliente)
    ficha.usuarios = ficha.usuarios_activos = 1
    return EmpresaCreada(
        empresa=ficha,
        acceso=ClaveEntregada(username=data.admin_username.strip().lower(),
                              clave_temporal=clave),
    )


class EmpresaCambios(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    logo_url: Optional[str] = None
    color: Optional[str] = None


@router.put("/empresas/{cliente_id}", response_model=EmpresaEnLista)
async def editar_empresa(
    cliente_id: int, data: EmpresaCambios, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.editar")),
):
    """El código no se toca: es el nombre del esquema, y cambiarlo dejaría
    todas sus tablas huérfanas."""
    cliente = await _empresa(db, cliente_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)
    await _anotar(db, request, "empresa.edicion", cliente.codigo)
    await db.commit(); await db.refresh(cliente)
    return EmpresaEnLista.model_validate(cliente)


@router.put("/empresas/{cliente_id}/estado", response_model=EmpresaEnLista)
async def cambiar_estado(
    cliente_id: int, activo: bool, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.editar")),
):
    """Suspende o reactiva el acceso. No borra nada.

    No hay borrado de empresas a propósito: eliminar una sería eliminar su
    esquema entero con todo lo que tenga dentro.
    """
    cliente = await _empresa(db, cliente_id)
    if cliente.es_operador and not activo:
        raise HTTPException(
            400,
            "No se puede suspender a la empresa que opera la plataforma: nadie "
            "podría volver a entrar a esta consola para reactivarla.",
        )
    cliente.activo = activo
    cliente.suspendido_desde = None if activo else datetime.utcnow()
    await _anotar(db, request, "empresa.reactivacion" if activo else "empresa.suspension",
                  cliente.codigo)
    await db.commit(); await db.refresh(cliente)
    return EmpresaEnLista.model_validate(cliente)


# ─── Usuarios de una empresa ──────────────────────────────────────────────────

async def _rol_id_de(s: AsyncSession, nombre: str) -> int:
    """El id del perfil que se llama así, dentro del esquema ya seleccionado.

    Se exige que exista: dejar el vínculo vacío no falla en ninguna parte, pero
    deja a la persona sin un solo permiso y sin nada que lo explique.
    """
    fila = (await s.execute(text("SELECT id FROM roles WHERE upper(nombre) = :n"),
                            {"n": (nombre or "").strip().upper()})).first()
    if not fila:
        raise HTTPException(
            400,
            f"Esa empresa no tiene un perfil «{nombre}». Créelo primero en la "
            f"pestaña Perfiles, o escoja uno de los que ya tiene.")
    return fila[0]


@router.get("/empresas/{cliente_id}/usuarios", response_model=List[UsuarioDeEmpresa])
async def listar_usuarios(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.ver")),
):
    cliente = await _empresa(db, cliente_id)
    async with _sesion_de(cliente.esquema) as s:
        r = await s.execute(select(Usuario).order_by(Usuario.username))
        return [UsuarioDeEmpresa.model_validate(u) for u in r.scalars().all()]


@router.post("/empresas/{cliente_id}/usuarios", response_model=ClaveEntregada, status_code=201)
async def crear_usuario(
    cliente_id: int, data: UsuarioNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.crear")),
):
    """Crea un usuario dentro de la empresa y devuelve su clave temporal."""
    cliente = await _empresa(db, cliente_id)
    usuario = data.username.strip().lower()
    clave = _clave_temporal()
    async with _sesion_de(cliente.esquema) as s:
        choque = await s.execute(
            select(func.count()).select_from(Usuario).where(
                (Usuario.username == usuario) | (Usuario.email == str(data.email))
            )
        )
        if choque.scalar():
            raise HTTPException(409, "Ya hay un usuario con ese nombre o ese correo en esta empresa")
        # El nombre y el id del perfil van juntos: el nombre es lo que se
        # muestra y el id es de donde salen los permisos.
        rol = (data.rol or "").strip().upper()
        s.add(Usuario(
            nombre=data.nombre.strip(), apellido=data.apellido.strip(),
            email=str(data.email), username=usuario,
            hashed_password=hash_password(clave),
            rol=rol, rol_id=await _rol_id_de(s, rol),
            cargo=data.cargo, activo=True,
        ))
    await _anotar(db, request, "usuario.alta", cliente.codigo, f"«{usuario}»")
    await db.commit()
    return ClaveEntregada(username=usuario, clave_temporal=clave)


@router.put("/empresas/{cliente_id}/usuarios/{usuario_id}", response_model=UsuarioDeEmpresa)
async def editar_usuario(
    cliente_id: int, usuario_id: int, data: UsuarioCambios, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.editar")),
):
    cliente = await _empresa(db, cliente_id)
    cambios = data.model_dump(exclude_unset=True)
    async with _sesion_de(cliente.esquema) as s:
        r = await s.execute(select(Usuario).where(Usuario.id == usuario_id))
        u = r.scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Ese usuario no existe en esta empresa")
        if cambios.get("activo") is False:
            # Dejar a una empresa sin ningún administrador activo la vuelve
            # inaccesible para su propia gente.
            quedan = await s.execute(text(
                "SELECT count(*) FROM usuarios "
                "WHERE activo AND rol = 'ADMINISTRADOR' AND id <> :id"), {"id": usuario_id})
            if u.rol == "ADMINISTRADOR" and not (quedan.scalar() or 0):
                raise HTTPException(
                    400,
                    "Es el único administrador activo de la empresa: si se desactiva, "
                    "nadie de esa empresa podría volver a entrar. Cree otro primero.",
                )
        if "rol" in cambios:
            cambios["rol"] = (cambios["rol"] or "").strip().upper()
            u.rol_id = await _rol_id_de(s, cambios["rol"])
        for campo, valor in cambios.items():
            setattr(u, campo, str(valor) if campo == "email" else valor)
        await s.flush()
        ficha = UsuarioDeEmpresa.model_validate(u)
    await _anotar(db, request, "usuario.edicion", cliente.codigo,
                  f"«{ficha.username}»: {', '.join(cambios) or 'sin cambios'}")
    await db.commit()
    return ficha


@router.post("/empresas/{cliente_id}/usuarios/{usuario_id}/clave", response_model=ClaveEntregada)
async def restablecer_clave(
    cliente_id: int, usuario_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.clave")),
):
    """Devuelve el acceso a un usuario bloqueado, con una clave de un solo uso.

    Es la vía para rescatar a una empresa que perdió a su administrador. Antes
    de existir esto, la única salida era entrar por SSH y escribir el hash a
    mano en la base.
    """
    cliente = await _empresa(db, cliente_id)
    clave = _clave_temporal()
    async with _sesion_de(cliente.esquema) as s:
        r = await s.execute(select(Usuario).where(Usuario.id == usuario_id))
        u = r.scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Ese usuario no existe en esta empresa")
        u.hashed_password = hash_password(clave)
        u.intentos_fallidos = 0
        u.bloqueado = False
        usuario = u.username
    await _anotar(db, request, "usuario.clave", cliente.codigo, f"«{usuario}»")
    await db.commit()
    return ClaveEntregada(username=usuario, clave_temporal=clave)


# ─── Bitácora ─────────────────────────────────────────────────────────────────

@router.get("/bitacora", response_model=List[AsientoBitacora])
async def ver_bitacora(
    empresa: Optional[str] = None, limite: int = 200,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("bitacora.ver")),
):
    q = select(PlataformaBitacora).order_by(PlataformaBitacora.fecha.desc())
    if empresa:
        q = q.where(PlataformaBitacora.empresa_codigo == empresa)
    r = await db.execute(q.limit(min(limite, 1000)))
    return [AsientoBitacora.model_validate(a) for a in r.scalars().all()]


# ══════════════════════════════════════════════════════════════════════════════
# LOS PERFILES DE UNA EMPRESA
# ══════════════════════════════════════════════════════════════════════════════
#
# Un perfil es el conjunto de pantallas que puede ver una persona dentro de su
# empresa. Existían desde el principio en `/roles`, pero ese camino solo sirve
# desde dentro de la propia empresa: la consola administra a todas, y no tiene
# —ni debe tener— una sesión abierta en cada una.
#
# Por eso estos endpoints entran por el esquema del cliente, igual que ya lo
# hacía la edición de usuarios. El operador administra desde afuera, y cada
# empresa sigue pudiendo administrarse a sí misma por su propio camino.

class PermisoDisponible(BaseModel):
    clave: str
    nombre: str
    grupo: str


@router.get("/permisos-perfil", response_model=List[PermisoDisponible])
async def permisos_de_perfil(_=Depends(exigir("empresas.ver"))):
    """Qué se puede marcar en un perfil.

    Lo sirve el servidor en vez de que la pantalla lo tenga escrito: era
    justamente lo que estaba desincronizado, y así agregar un módulo nuevo lo
    hace aparecer solo en la consola.
    """
    return [PermisoDisponible(clave=p.clave, nombre=p.nombre, grupo=p.grupo)
            for p in PERMISOS_PERFIL]


class PerfilDeEmpresa(BaseModel):
    id: int
    nombre: str
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: Optional[str] = None
    permisos: dict
    es_sistema: bool = False
    total_usuarios: int = 0


class PerfilNuevo(BaseModel):
    nombre: str
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: Optional[str] = "#6366f1"
    permisos: dict = {}


class PerfilCambios(BaseModel):
    """Todo opcional: se manda solo lo que cambia."""
    nombre: Optional[str] = None
    label: Optional[str] = None
    descripcion: Optional[str] = None
    color: Optional[str] = None
    permisos: Optional[dict] = None


async def _perfiles_de(esquema: str) -> List[PerfilDeEmpresa]:
    async with _sesion_de(esquema) as s:
        filas = (await s.execute(text(
            "SELECT id, nombre, label, descripcion, color, permisos, es_sistema "
            "FROM roles ORDER BY es_sistema DESC, nombre"))).all()
        # Cuántos los usan: un perfil con gente adentro no se puede borrar sin
        # dejar a esa gente sin permisos.
        conteo = {n: c for n, c in (await s.execute(text(
            "SELECT rol, count(*) FROM usuarios WHERE activo GROUP BY rol"))).all()}
    return [
        PerfilDeEmpresa(
            id=f[0], nombre=f[1], label=f[2], descripcion=f[3], color=f[4],
            permisos=normalizar_permisos(f[5]), es_sistema=bool(f[6]),
            total_usuarios=conteo.get(f[1], 0),
        )
        for f in filas
    ]


@router.get("/empresas/{cliente_id}/perfiles", response_model=List[PerfilDeEmpresa])
async def listar_perfiles(
    cliente_id: int,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("empresas.ver")),
):
    cliente = await _empresa(db, cliente_id)
    return await _perfiles_de(cliente.esquema)


@router.post("/empresas/{cliente_id}/perfiles", response_model=PerfilDeEmpresa,
             status_code=201)
async def crear_perfil(
    cliente_id: int, data: PerfilNuevo, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.editar")),
):
    cliente = await _empresa(db, cliente_id)
    nombre = (data.nombre or "").strip().upper()
    if not nombre:
        raise HTTPException(400, "El perfil necesita un nombre")

    async with _sesion_de(cliente.esquema) as s:
        ya = await s.execute(text("SELECT 1 FROM roles WHERE upper(nombre) = :n"),
                             {"n": nombre})
        if ya.scalar():
            raise HTTPException(409, f"Esa empresa ya tiene un perfil «{nombre}»")
        r = await s.execute(text(
            "INSERT INTO roles (nombre, label, descripcion, color, permisos, "
            "es_sistema, created_at, updated_at) "
            "VALUES (:n, :l, :d, :c, CAST(:p AS jsonb), false, now(), now()) "
            "RETURNING id"), {
                "n": nombre, "l": data.label or data.nombre,
                "d": data.descripcion, "c": data.color or "#6366f1",
                "p": json.dumps(normalizar_permisos(data.permisos))})
        nuevo = r.scalar()

    await _anotar(db, request, "perfil.creacion", cliente.codigo, f"«{nombre}»")
    await db.commit()
    perfiles = await _perfiles_de(cliente.esquema)
    return next(p for p in perfiles if p.id == nuevo)


@router.put("/empresas/{cliente_id}/perfiles/{perfil_id}", response_model=PerfilDeEmpresa)
async def editar_perfil(
    cliente_id: int, perfil_id: int, data: PerfilCambios, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.editar")),
):
    cliente = await _empresa(db, cliente_id)
    cambios = data.model_dump(exclude_unset=True)

    async with _sesion_de(cliente.esquema) as s:
        actual = (await s.execute(text(
            "SELECT nombre, es_sistema FROM roles WHERE id = :i"),
            {"i": perfil_id})).first()
        if not actual:
            raise HTTPException(404, "Ese perfil no existe en esta empresa")

        # El perfil de administrador se puede renombrar y describir, pero no
        # recortar: quitarle permisos deja a la empresa sin quien administre
        # su propia gente, y solo la consola podría devolvérselos.
        if actual[0] == "ADMINISTRADOR" and "permisos" in cambios:
            raise HTTPException(
                409,
                "El perfil ADMINISTRADOR no puede quedarse sin permisos: es el "
                "único que puede volver a repartirlos dentro de la empresa.")

        sets, valores = [], {"i": perfil_id}
        for campo in ("nombre", "label", "descripcion", "color"):
            if campo in cambios:
                sets.append(f"{campo} = :{campo}")
                valores[campo] = (cambios[campo] or "").strip().upper() \
                    if campo == "nombre" else cambios[campo]
        if "permisos" in cambios:
            sets.append("permisos = CAST(:permisos AS jsonb)")
            valores["permisos"] = json.dumps(normalizar_permisos(cambios["permisos"]))
        if not sets:
            raise HTTPException(400, "No hay nada que cambiar")
        sets.append("updated_at = now()")

        # Renombrar el perfil tiene que arrastrar a quienes lo tienen: el
        # usuario guarda el nombre del rol, no solo su id, y si se cambia uno
        # sin el otro esa gente se queda con un perfil que ya no existe.
        if "nombre" in cambios:
            await s.execute(text("UPDATE usuarios SET rol = :nuevo WHERE rol = :viejo"),
                            {"nuevo": valores["nombre"], "viejo": actual[0]})
        await s.execute(text(f"UPDATE roles SET {', '.join(sets)} WHERE id = :i"),
                        valores)

    await _anotar(db, request, "perfil.edicion", cliente.codigo,
                  f"«{actual[0]}»: {', '.join(cambios)}")
    await db.commit()
    perfiles = await _perfiles_de(cliente.esquema)
    return next(p for p in perfiles if p.id == perfil_id)


@router.delete("/empresas/{cliente_id}/perfiles/{perfil_id}", status_code=204)
async def borrar_perfil(
    cliente_id: int, perfil_id: int, request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("usuarios.editar")),
):
    cliente = await _empresa(db, cliente_id)
    async with _sesion_de(cliente.esquema) as s:
        fila = (await s.execute(text(
            "SELECT nombre, es_sistema FROM roles WHERE id = :i"),
            {"i": perfil_id})).first()
        if not fila:
            raise HTTPException(404, "Ese perfil no existe en esta empresa")
        if fila[1]:
            raise HTTPException(
                409, "Ese perfil es del sistema y no se puede eliminar.")
        usando = (await s.execute(text(
            "SELECT count(*) FROM usuarios WHERE rol = :n AND activo"),
            {"n": fila[0]})).scalar() or 0
        if usando:
            raise HTTPException(
                409,
                f"Hay {usando} usuario(s) con ese perfil. Cámbieles el perfil "
                f"antes de eliminarlo, o se quedarían sin permisos.")
        await s.execute(text("DELETE FROM roles WHERE id = :i"), {"i": perfil_id})

    await _anotar(db, request, "perfil.borrado", cliente.codigo, f"«{fila[0]}»")
    await db.commit()


# ─── Fallos de la interfaz ────────────────────────────────────────────────────

class FalloInterfaz(BaseModel):
    referencia: str
    mensaje: str
    pila: Optional[str] = None
    ruta: Optional[str] = None
    navegador: Optional[str] = None
    cliente: Optional[str] = None


@router.post("/fallo-interfaz", status_code=204)
async def registrar_fallo_interfaz(
    datos: FalloInterfaz,
    request: Request,
    db: AsyncSession = Depends(get_db_plataforma),
):
    """Deja constancia de una pantalla que se rompió en el navegador de alguien.

    POR QUÉ NO PIDE SESIÓN
    Porque los fallos que más importan ocurren justamente cuando algo está mal:
    una sesión a medias, un token que no se pudo leer, la pantalla de ingreso
    que revienta. Exigir credenciales aquí dejaría fuera del registro los casos
    peores, que son los que hay que ver.

    No se confía en nada de lo que llega: se recorta, y lo único que se guarda es
    texto. Va a la bitácora de la plataforma, que ya existe para dejar rastro y
    vive en `public`, fuera del alcance de cualquier cliente.

    Responde 204 siempre. Si el registro falla, el usuario ya tiene bastante con
    su pantalla rota: no se le devuelve un segundo error por haberla reportado.
    """
    try:
        # Quién estaba: se lee del token si viene, y si no viene no pasa nada.
        # El navegador guarda la empresa activa como objeto JSON ({"codigo": ...});
        # se guardaba entero en una columna de 40 caracteres, el INSERT fallaba y
        # ningún fallo de interfaz quedaba registrado. Se toma solo el código.
        cliente = (datos.cliente or "").strip()
        if cliente.startswith("{"):
            try:
                cliente = str(__import__("json").loads(cliente).get("codigo") or "")
            except Exception:
                cliente = ""
        actor, empresa = "anónimo", (cliente or "desconocida")[:40]
        cabecera = request.headers.get("authorization") or ""
        if cabecera.lower().startswith("bearer "):
            try:
                claves = decode_token(cabecera[7:])
                actor = str(claves.get("usr") or claves.get("sub") or actor)[:80]
                empresa = str(claves.get("cli") or empresa)[:40]
            except Exception:
                pass   # un token vencido no impide registrar el fallo

        # El detalle cabe en 500 caracteres: se prioriza lo que sirve para
        # reproducir —la ruta y el mensaje— sobre la pila, que se recorta.
        detalle = (
            f"[{datos.referencia[:12]}] {(datos.ruta or '?')[:80]} · "
            f"{datos.mensaje[:220]} · {(datos.navegador or '')[:80]} · "
            f"{(datos.pila or '')[:100]}"
        )[:500]

        db.add(PlataformaBitacora(
            fecha=datetime.utcnow(), actor=actor, actor_empresa=empresa,
            accion="fallo_interfaz", empresa_codigo=(cliente[:40] or None),
            detalle=detalle))
        await db.commit()
    except Exception:
        # Nunca hacia arriba: esto es telemetría, no una operación del negocio.
        # Se deshace la transacción: si no, la dependencia intenta confirmarla al
        # salir y el error que se quiso callar vuelve como un 500.
        await db.rollback()


# ─── Los fallos de la interfaz, para la consola ───────────────────────────────
#
# POR QUÉ AGRUPADOS Y NO UNO POR UNO
# Quinientas apariciones del mismo error son UN problema, no quinientos. Una
# lista cronológica de fallos se vuelve ilegible en el primer error que afecte a
# varios clientes, y esconde justamente lo que hay que ver: cuál se repite más y
# a cuánta gente le está pasando.
#
# La agrupación es por mensaje normalizado. Se quitan los identificadores —el
# hash del archivo compilado, los números de línea, los ids— porque
# «MESPlanta-DbefsU82.js» y «MESPlanta-Kx91mZ4.js» son el mismo fallo con dos
# despliegues distintos, y contarlos aparte multiplica el ruido.


def _firma(mensaje: str) -> str:
    """Reduce un mensaje a lo que lo hace único, sin lo que cambia entre casos."""
    t = mensaje or ""
    t = re.sub(r"-[A-Za-z0-9_]{6,}\.js", ".js", t)   # hash del archivo compilado
    t = re.sub(r"https?://[^\s]+/", "", t)           # dominio y ruta
    t = re.sub(r"\b\d+\b", "N", t)                   # ids, líneas, columnas
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t[:180]


class FalloAgrupado(BaseModel):
    firma: str
    mensaje: str
    veces: int
    empresas: List[str]
    rutas: List[str]
    primera: Optional[datetime] = None
    ultima: Optional[datetime] = None
    referencia: Optional[str] = None
    incidencia_id: Optional[int] = None
    incidencia_clave: Optional[str] = None


async def _agrupar_fallos(db: AsyncSession, dias: int,
                          incluir_atendidos: bool) -> List["FalloAgrupado"]:
    """Agrupa los fallos registrados. La usan el listado y la conversión.

    Va como función y no se llama al endpoint desde el otro: invocar una ruta
    como si fuera una función obliga a inventarle valores a sus dependencias, y
    deja de compilar en cuanto alguien le agrega una.
    """
    desde = datetime.utcnow() - timedelta(days=max(1, min(dias, 365)))
    filas = (await db.execute(
        select(PlataformaBitacora)
        .where(PlataformaBitacora.accion == "fallo_interfaz",
               PlataformaBitacora.fecha >= desde)
        .order_by(PlataformaBitacora.fecha.desc())
        .limit(5000)
    )).scalars().all()

    # Qué grupos ya se convirtieron en incidencia.
    atendidos = {
        b.detalle.split("|")[0]: b
        for b in (await db.execute(
            select(PlataformaBitacora).where(
                PlataformaBitacora.accion == "fallo_convertido"))).scalars().all()
        if b.detalle and "|" in b.detalle
    }

    grupos: Dict[str, dict] = {}
    for fila in filas:
        detalle = fila.detalle or ""
        # El detalle se guardó como «[REF] ruta · mensaje · navegador · pila».
        partes = [p.strip() for p in detalle.split("·")]
        referencia = ""
        ruta = ""
        if partes and partes[0].startswith("["):
            cabeza = partes[0]
            cierre = cabeza.find("]")
            referencia = cabeza[1:cierre] if cierre > 0 else ""
            ruta = cabeza[cierre + 1:].strip()
        mensaje = partes[1] if len(partes) > 1 else detalle

        firma = _firma(mensaje)
        g = grupos.setdefault(firma, {
            "firma": firma, "mensaje": mensaje[:220], "veces": 0,
            "empresas": set(), "rutas": set(),
            "primera": fila.fecha, "ultima": fila.fecha,
            "referencia": referencia or None,
        })
        g["veces"] += 1
        if fila.empresa_codigo:
            g["empresas"].add(fila.empresa_codigo)
        elif fila.actor_empresa and fila.actor_empresa != "desconocida":
            g["empresas"].add(fila.actor_empresa)
        if ruta:
            g["rutas"].add(ruta[:60])
        g["primera"] = min(g["primera"], fila.fecha)
        g["ultima"] = max(g["ultima"], fila.fecha)

    salida = []
    for firma, g in grupos.items():
        marca = atendidos.get(firma)
        if marca is not None and not incluir_atendidos:
            continue
        clave = incidencia = None
        if marca is not None and marca.detalle:
            trozos = marca.detalle.split("|")
            if len(trozos) >= 3:
                try:
                    incidencia = int(trozos[1])
                except ValueError:
                    incidencia = None
                clave = trozos[2] or None
        salida.append(FalloAgrupado(
            firma=firma, mensaje=g["mensaje"], veces=g["veces"],
            empresas=sorted(g["empresas"])[:8],
            rutas=sorted(g["rutas"])[:8],
            primera=g["primera"], ultima=g["ultima"],
            referencia=g["referencia"],
            incidencia_id=incidencia, incidencia_clave=clave,
        ))
    salida.sort(key=lambda f: (-f.veces, f.mensaje))
    return salida


@router.get("/fallos", response_model=List[FalloAgrupado])
async def listar_fallos(
    dias: int = 30,
    incluir_atendidos: bool = False,
    db: AsyncSession = Depends(get_db_plataforma),
    _=Depends(exigir("bitacora.ver")),
):
    """Lo que se está rompiendo en los navegadores, agrupado y ordenado.

    Ordena por cuántas veces ocurrió, no por cuándo: lo que más se repite es lo
    que hay que arreglar primero, aunque el último caso sea de anteayer.
    """
    return await _agrupar_fallos(db, dias, incluir_atendidos)


class ConvertirFallo(BaseModel):
    firma: str
    resumen: Optional[str] = None
    proyecto_id: Optional[int] = None


@router.post("/fallos/incidencia", status_code=201)
async def fallo_a_incidencia(
    datos: ConvertirFallo,
    db: AsyncSession = Depends(get_db_plataforma),
    quien: Miembro = Depends(exigir("bitacora.ver")),
):
    """Convierte un grupo de fallos en una incidencia del equipo.

    Se hace DESPUÉS de revisar, y a mano, a propósito: convertir cada fallo
    automáticamente llenaría el tablero de duplicados y de errores de un solo
    navegador raro. Quien revisa decide cuál merece trabajo.

    La incidencia nace con el recuento, las empresas afectadas y las rutas: es lo
    que hace falta para reproducir, y buscarlo después obliga a volver a esta
    pantalla.
    """
    from app.core import gestion_incidencias as _gi
    from app.infrastructure.models.gestion import (
        GPEstado, GPProyecto, GPTipoIncidencia,
    )

    # Se recalcula el grupo para que la incidencia lleve cifras de ahora y no las
    # que la pantalla tenía cargadas hace media hora.
    grupos = await _agrupar_fallos(db, dias=90, incluir_atendidos=True)
    grupo = next((g for g in grupos if g.firma == datos.firma), None)
    if grupo is None:
        raise HTTPException(404, "Ese fallo ya no aparece en los últimos 90 días.")
    if grupo.incidencia_id:
        raise HTTPException(
            409, f"Ese fallo ya está en la incidencia {grupo.incidencia_clave}.")

    proyecto = None
    if datos.proyecto_id:
        proyecto = (await db.execute(select(GPProyecto).where(
            GPProyecto.id == datos.proyecto_id))).scalar_one_or_none()
    if proyecto is None:
        proyecto = (await db.execute(select(GPProyecto).where(
            GPProyecto.incidencia_automatica.is_(True),
            GPProyecto.archivado.is_(False),
        ).order_by(GPProyecto.id).limit(1))).scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(
            409, "No hay ningún proyecto donde registrarla. Escoja uno, o marque "
                 "«recibe las solicitudes de soporte» en el que corresponda.")

    tipo = (await db.execute(select(GPTipoIncidencia).where(
        GPTipoIncidencia.clave == "ERROR",
        GPTipoIncidencia.archivado.is_(False),
        or_(GPTipoIncidencia.proyecto_id == proyecto.id,
            GPTipoIncidencia.proyecto_id.is_(None)),
    ).order_by(GPTipoIncidencia.proyecto_id.desc().nullslast())
      .limit(1))).scalar_one_or_none()
    if tipo is None:
        raise HTTPException(409, "No hay un tipo «Error» configurado.")

    workflow_id = await _gi.workflow_de(db, proyecto, tipo)
    inicial = (await db.execute(select(GPEstado).where(
        GPEstado.workflow_id == workflow_id,
    ).order_by(GPEstado.orden).limit(1))).scalar_one_or_none()

    empresas = ", ".join(grupo.empresas) or "sin identificar"
    rutas = "\n".join(f"  · {r}" for r in grupo.rutas) or "  · sin registrar"
    descripcion = (
        f"Fallo de la interfaz reportado automáticamente por los navegadores.\n\n"
        f"Mensaje:\n  {grupo.mensaje}\n\n"
        f"Ocurrió {grupo.veces} vez/veces entre {grupo.primera:%Y-%m-%d %H:%M} "
        f"y {grupo.ultima:%Y-%m-%d %H:%M}.\n"
        f"Empresas afectadas: {empresas}.\n"
        f"Pantallas:\n{rutas}\n\n"
        f"Referencia de un caso: {grupo.referencia or '—'}."
    )

    incidencia = await _gi.crear(
        db, proyecto, tipo_id=tipo.id,
        resumen=(datos.resumen or f"Fallo de interfaz: {grupo.mensaje}")[:300],
        descripcion=descripcion, autor=quien.usuario,
        campos={}, estado_id=inicial.id if inicial else None,
    )
    await db.flush()

    # Se marca el grupo como atendido para que no vuelva a aparecer como nuevo.
    # Va en la misma bitácora y no en una tabla aparte: es un hecho más de lo que
    # el operador hizo, que es exactamente para lo que existe.
    db.add(PlataformaBitacora(
        fecha=datetime.utcnow(),
        actor=quien.usuario, actor_empresa="tittanware",
        accion="fallo_convertido", empresa_codigo=None,
        detalle=f"{grupo.firma}|{incidencia.id}|{incidencia.clave}"[:500]))
    await db.commit()
    await db.refresh(incidencia)
    return {"id": incidencia.id, "clave": incidencia.clave,
            "proyecto": proyecto.nombre,
            "mensaje": f"{incidencia.clave} creada con {grupo.veces} caso(s)."}
