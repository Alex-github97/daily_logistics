"""
Contrato común de los conectores de marketplaces.

Cada plataforma traduce sus pedidos y publicaciones a estas estructuras
normalizadas, y el resto del sistema (ingreso de pedidos, stock, estados)
trabaja solo con ellas. Agregar una plataforma nueva es escribir un adaptador.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


class ErrorConector(Exception):
    """Falla al hablar con la plataforma (credenciales, red, respuesta inválida)."""


@dataclass
class LineaNorm:
    cantidad: float
    ref_externa: Optional[str] = None      # id de la publicación / producto en la plataforma
    ref_variante: Optional[str] = None     # id de la variante (si aplica)
    sku: Optional[str] = None              # SKU que el vendedor puso en la plataforma
    titulo: Optional[str] = None
    precio: Optional[float] = None


@dataclass
class PedidoNorm:
    pedido_externo: str
    lineas: List[LineaNorm]
    estado_externo: Optional[str] = None
    pagado: bool = True                    # solo los pagados comprometen inventario
    cancelado: bool = False
    fecha: Optional[datetime] = None
    comprador: Optional[str] = None
    documento: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    total: Optional[float] = None
    envio_externo: Optional[str] = None
    crudo: Optional[Dict[str, Any]] = None


@dataclass
class PublicacionNorm:
    ref_externa: str
    ref_variante: str = ""
    ref_inventario: Optional[str] = None
    sku: Optional[str] = None
    titulo: Optional[str] = None


@dataclass
class Capacidades:
    """Qué sabe hacer el conector con la API de su plataforma."""
    pedidos_api: bool = True
    stock: bool = True
    envio: bool = True
    entrega: bool = True
    publicaciones: bool = True
    webhook: bool = True
    oauth: bool = False
    notas: List[str] = field(default_factory=list)


class Adaptador:
    """Base de los adaptadores. `credenciales` y `config` son los del conector;
    si el adaptador renueva un token, lo deja en `self.credenciales` y quien lo
    llamó lo guarda."""

    tipo = ""
    capacidades = Capacidades()

    def __init__(self, credenciales: Dict[str, Any], config: Dict[str, Any]):
        self.credenciales = dict(credenciales or {})
        self.config = dict(config or {})
        self.credenciales_cambiaron = False

    # ── HTTP ──────────────────────────────────────────────────────────────────
    async def _http(self, metodo: str, url: str, **kw) -> Any:
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.request(metodo, url, **kw)
        except httpx.HTTPError as e:
            raise ErrorConector(f"No se pudo conectar con {self.tipo}: {e}") from e
        if r.status_code >= 400:
            raise ErrorConector(f"{self.tipo} respondió {r.status_code}: {r.text[:400]}")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def _cred(self, clave: str) -> str:
        v = (self.credenciales.get(clave) or "").strip()
        if not v:
            raise ErrorConector(f"Falta configurar «{clave}» en el conector.")
        return v

    # ── Operaciones (cada adaptador implementa las que su plataforma permite) ──
    async def probar(self) -> str:
        raise NotImplementedError

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        return []

    async def pedido(self, ref: str) -> Optional[PedidoNorm]:
        return None

    async def publicaciones(self) -> List[PublicacionNorm]:
        return []

    async def publicar_stock(self, pub, cantidad: int) -> None:
        raise ErrorConector(f"{self.tipo}: la actualización de stock no está disponible.")

    async def confirmar_recepcion(self, pedido) -> None:
        """Avisar a la plataforma que el pedido se tomó (algunas lo exigen)."""

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        """Devuelve un id de envío de la plataforma, si lo hay (para marcar entregado)."""
        return None

    async def marcar_entregado(self, pedido) -> None:
        pass

    def refs_de_webhook(self, cuerpo: Any, encabezados: Dict[str, str]) -> List[str]:
        """Del aviso recibido, qué pedidos hay que consultar."""
        return []

    def pedido_de_webhook(self, cuerpo: Any) -> Optional[PedidoNorm]:
        """Si el aviso ya trae el pedido completo, normalizarlo sin consultar."""
        return None

    def verificar_firma(self, crudo: bytes, encabezados: Dict[str, str]) -> bool:
        return True


def num(v, defecto=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


def fecha(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
