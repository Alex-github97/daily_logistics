"""
Adaptadores por plataforma.

Cada uno sigue la documentación oficial de su API. Los puntos que dependen de
cómo esté configurada la cuenta del vendedor (modalidad de envío, permisos de
la app) se indican en `capacidades.notas` y se ven en la pantalla del conector.

`config["api_base"]` permite apuntar a un entorno de pruebas (sandbox) o a un
simulador; si no se da, se usa la URL de producción de la plataforma.
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from app.core.marketplace.base import (
    Adaptador, Capacidades, ErrorConector, LineaNorm, PedidoNorm, PublicacionNorm, fecha, num,
)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ═════════════════════════════════════════════════════════════════════════════
# MercadoLibre
# ═════════════════════════════════════════════════════════════════════════════
class MercadoLibre(Adaptador):
    """API REST de MercadoLibre (developers.mercadolibre.com).

    Autorización OAuth: el vendedor autoriza la app y se guardan access_token y
    refresh_token (el access_token dura ~6 horas y se renueva solo)."""
    tipo = "MERCADOLIBRE"
    capacidades = Capacidades(oauth=True, notas=[
        "Requiere crear una aplicación en el portal de desarrolladores de MercadoLibre (client_id y client_secret) "
        "y que el vendedor la autorice con «Conectar con MercadoLibre».",
        "Los avisos (tema orders_v2) llegan a la URL pública del conector: configúrela en la aplicación de MercadoLibre.",
        "Marcar enviado/entregado aplica a envíos que gestiona el vendedor (Mercado Envíos 1 / acordar con el comprador). "
        "Con Mercado Envíos 2 el estado lo maneja MercadoLibre. Validar con la cuenta real antes de producción.",
    ])

    @property
    def api(self) -> str:
        return (self.config.get("api_base") or "https://api.mercadolibre.com").rstrip("/")

    @property
    def auth(self) -> str:
        return (self.config.get("auth_base") or "https://auth.mercadolibre.com.co").rstrip("/")

    def url_autorizacion(self, redirect_uri: str, estado: str) -> str:
        return f"{self.auth}/authorization?" + urlencode({
            "response_type": "code", "client_id": self._cred("client_id"),
            "redirect_uri": redirect_uri, "state": estado})

    async def canjear_codigo(self, codigo: str, redirect_uri: str) -> None:
        r = await self._http("POST", f"{self.api}/oauth/token", data={
            "grant_type": "authorization_code", "client_id": self._cred("client_id"),
            "client_secret": self._cred("client_secret"), "code": codigo, "redirect_uri": redirect_uri})
        self._guardar_token(r)

    def _guardar_token(self, r: Dict[str, Any]) -> None:
        self.credenciales.update({
            "access_token": r["access_token"], "refresh_token": r.get("refresh_token") or self.credenciales.get("refresh_token"),
            "user_id": str(r.get("user_id") or self.credenciales.get("user_id") or ""),
            "expira": (datetime.now(timezone.utc) + timedelta(seconds=int(r.get("expires_in", 21600)) - 300)).isoformat()})
        self.credenciales_cambiaron = True

    async def _token(self) -> str:
        exp = fecha(self.credenciales.get("expira"))
        if not self.credenciales.get("access_token") or (exp and exp <= datetime.now(timezone.utc)):
            if not self.credenciales.get("refresh_token"):
                raise ErrorConector("MercadoLibre: falta autorizar la cuenta («Conectar con MercadoLibre»).")
            r = await self._http("POST", f"{self.api}/oauth/token", data={
                "grant_type": "refresh_token", "client_id": self._cred("client_id"),
                "client_secret": self._cred("client_secret"), "refresh_token": self.credenciales["refresh_token"]})
            self._guardar_token(r)
        return self.credenciales["access_token"]

    async def _get(self, ruta: str, **params) -> Any:
        return await self._http("GET", f"{self.api}{ruta}", params=params or None,
                                headers={"Authorization": f"Bearer {await self._token()}"})

    async def _put(self, ruta: str, cuerpo: Dict[str, Any]) -> Any:
        return await self._http("PUT", f"{self.api}{ruta}", json=cuerpo,
                                headers={"Authorization": f"Bearer {await self._token()}"})

    async def probar(self) -> str:
        me = await self._get("/users/me")
        self.credenciales["user_id"] = str(me.get("id"))
        self.credenciales_cambiaron = True
        return f"Cuenta {me.get('nickname')} ({me.get('site_id')})"

    def _normalizar(self, o: Dict[str, Any], envio: Optional[Dict[str, Any]] = None) -> PedidoNorm:
        buyer = o.get("buyer") or {}
        dir_ = (envio or {}).get("receiver_address") or {}
        lineas = []
        for it in o.get("order_items") or []:
            item = it.get("item") or {}
            lineas.append(LineaNorm(
                cantidad=num(it.get("quantity"), 0), ref_externa=item.get("id"),
                ref_variante=str(item.get("variation_id") or ""), sku=item.get("seller_sku") or item.get("seller_custom_field"),
                titulo=item.get("title"), precio=num(it.get("unit_price"))))
        estado = o.get("status")
        return PedidoNorm(
            pedido_externo=str(o["id"]), lineas=lineas, estado_externo=estado,
            pagado=estado == "paid", cancelado=estado in ("cancelled", "invalid"),
            fecha=fecha(o.get("date_created")),
            comprador=" ".join(x for x in (buyer.get("first_name"), buyer.get("last_name")) if x) or buyer.get("nickname"),
            direccion=" ".join(x for x in (dir_.get("address_line"), dir_.get("comment")) if x) or None,
            ciudad=(dir_.get("city") or {}).get("name"), telefono=(dir_.get("receiver_phone") or None),
            total=num(o.get("total_amount")),
            envio_externo=str((o.get("shipping") or {}).get("id") or "") or None, crudo=o)

    async def pedido(self, ref: str) -> Optional[PedidoNorm]:
        o = await self._get(f"/orders/{ref}")
        envio = None
        sid = (o.get("shipping") or {}).get("id")
        if sid:
            try:
                envio = await self._get(f"/shipments/{sid}")
            except ErrorConector:
                envio = None
        return self._normalizar(o, envio)

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        uid = self.credenciales.get("user_id") or (await self._get("/users/me")).get("id")
        r = await self._get("/orders/search", seller=uid, sort="date_desc", limit=50,
                            **{"order.date_created.from": _iso(desde)})
        salida = []
        for o in (r or {}).get("results", []):
            salida.append(await self.pedido(str(o["id"])))
        return salida

    async def publicaciones(self) -> List[PublicacionNorm]:
        uid = self.credenciales.get("user_id") or (await self._get("/users/me")).get("id")
        ids, offset = [], 0
        while True:
            r = await self._get(f"/users/{uid}/items/search", limit=100, offset=offset)
            ids += r.get("results", [])
            offset += 100
            if offset >= (r.get("paging") or {}).get("total", 0) or offset >= 2000:
                break
        salida = []
        for i in range(0, len(ids), 20):
            for res in await self._get("/items", ids=",".join(ids[i:i + 20])) or []:
                it = res.get("body") or {}
                sku_item = it.get("seller_custom_field") or next(
                    (a.get("value_name") for a in it.get("attributes") or [] if a.get("id") == "SELLER_SKU"), None)
                variaciones = it.get("variations") or []
                if not variaciones:
                    salida.append(PublicacionNorm(ref_externa=it.get("id"), sku=sku_item, titulo=it.get("title")))
                for v in variaciones:
                    sku_v = v.get("seller_custom_field") or next(
                        (a.get("value_name") for a in v.get("attributes") or [] if a.get("id") == "SELLER_SKU"), None)
                    salida.append(PublicacionNorm(ref_externa=it.get("id"), ref_variante=str(v.get("id")),
                                                  sku=sku_v or sku_item, titulo=it.get("title")))
        return salida

    async def publicar_stock(self, pub, cantidad: int) -> None:
        if pub.ref_variante:
            await self._put(f"/items/{pub.ref_externa}",
                            {"variations": [{"id": int(pub.ref_variante), "available_quantity": cantidad}]})
        else:
            await self._put(f"/items/{pub.ref_externa}", {"available_quantity": cantidad})

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        if pedido.envio_externo:
            await self._put(f"/shipments/{pedido.envio_externo}",
                            {"tracking_number": tracking, "status": "shipped"})
        return pedido.envio_externo

    async def marcar_entregado(self, pedido) -> None:
        if pedido.envio_externo:
            await self._put(f"/shipments/{pedido.envio_externo}", {"status": "delivered"})

    def refs_de_webhook(self, cuerpo: Any, encabezados: Dict[str, str]) -> List[str]:
        if isinstance(cuerpo, dict) and cuerpo.get("topic") in ("orders_v2", "orders"):
            return [str(cuerpo.get("resource", "")).rstrip("/").split("/")[-1]]
        return []


# ═════════════════════════════════════════════════════════════════════════════
# Shopify (GraphQL Admin API)
# ═════════════════════════════════════════════════════════════════════════════
class Shopify(Adaptador):
    tipo = "SHOPIFY"
    capacidades = Capacidades(notas=[
        "Use una app personalizada de Shopify con permisos de pedidos, productos, inventario y fulfillments, "
        "y copie su Admin API access token.",
        "El ID de ubicación (location) es la bodega de Shopify cuyo inventario se actualiza.",
        "Para avisos inmediatos, cree el webhook «orders/create» apuntando a la URL pública del conector.",
    ])

    @property
    def url(self) -> str:
        base = self.config.get("api_base") or f"https://{self._cred('tienda')}"
        return f"{base.rstrip('/')}/admin/api/{self.config.get('api_version') or '2026-01'}/graphql.json"

    async def _gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = await self._http("POST", self.url, json={"query": query, "variables": variables or {}},
                             headers={"X-Shopify-Access-Token": self._cred("access_token")})
        if r.get("errors"):
            raise ErrorConector(f"Shopify: {json.dumps(r['errors'])[:400]}")
        return r["data"]

    async def probar(self) -> str:
        d = await self._gql("{ shop { name myshopifyDomain } }")
        return f"Tienda {d['shop']['name']} ({d['shop']['myshopifyDomain']})"

    _CAMPOS = """id name createdAt cancelledAt displayFinancialStatus
      totalPriceSet { shopMoney { amount } }
      customer { firstName lastName email phone }
      shippingAddress { name address1 address2 city phone }
      lineItems(first: 100) { nodes { sku title quantity
        originalUnitPriceSet { shopMoney { amount } }
        variant { id inventoryItem { id } } product { id } } }"""

    def _normalizar(self, o: Dict[str, Any]) -> PedidoNorm:
        cli = o.get("customer") or {}
        dir_ = o.get("shippingAddress") or {}
        lineas = [LineaNorm(cantidad=num(li.get("quantity"), 0), ref_externa=(li.get("product") or {}).get("id"),
                            ref_variante=(li.get("variant") or {}).get("id") or "", sku=li.get("sku"),
                            titulo=li.get("title"),
                            precio=num(((li.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get("amount")))
                  for li in (o.get("lineItems") or {}).get("nodes", [])]
        financiero = (o.get("displayFinancialStatus") or "").upper()
        return PedidoNorm(
            pedido_externo=o["id"], lineas=lineas, estado_externo=financiero,
            pagado=financiero in ("PAID", "PARTIALLY_REFUNDED"), cancelado=bool(o.get("cancelledAt")),
            fecha=fecha(o.get("createdAt")),
            comprador=dir_.get("name") or " ".join(x for x in (cli.get("firstName"), cli.get("lastName")) if x),
            email=cli.get("email"), telefono=dir_.get("phone") or cli.get("phone"),
            direccion=" ".join(x for x in (dir_.get("address1"), dir_.get("address2")) if x) or None,
            ciudad=dir_.get("city"), total=num(((o.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")),
            crudo={"name": o.get("name"), "id": o["id"]})

    async def pedido(self, ref: str) -> Optional[PedidoNorm]:
        d = await self._gql(f"query($id: ID!) {{ order(id: $id) {{ {self._CAMPOS} }} }}", {"id": ref})
        return self._normalizar(d["order"]) if d.get("order") else None

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        d = await self._gql(f"""query($q: String!) {{ orders(first: 50, query: $q, sortKey: CREATED_AT, reverse: true)
            {{ nodes {{ {self._CAMPOS} }} }} }}""", {"q": f"created_at:>='{_iso(desde)}'"})
        return [self._normalizar(o) for o in d["orders"]["nodes"]]

    async def publicaciones(self) -> List[PublicacionNorm]:
        salida, despues = [], None
        for _ in range(20):
            d = await self._gql("""query($after: String) { productVariants(first: 100, after: $after) {
                nodes { id sku title product { id title } inventoryItem { id } }
                pageInfo { hasNextPage endCursor } } }""", {"after": despues})
            pv = d["productVariants"]
            for v in pv["nodes"]:
                salida.append(PublicacionNorm(
                    ref_externa=v["product"]["id"], ref_variante=v["id"], ref_inventario=(v.get("inventoryItem") or {}).get("id"),
                    sku=v.get("sku"), titulo=f"{v['product']['title']} · {v.get('title')}"))
            if not pv["pageInfo"]["hasNextPage"]:
                break
            despues = pv["pageInfo"]["endCursor"]
        return salida

    async def publicar_stock(self, pub, cantidad: int) -> None:
        if not pub.ref_inventario:
            raise ErrorConector("Shopify: la publicación no tiene inventory item (vuelva a traer las publicaciones).")
        d = await self._gql("""mutation($input: InventorySetQuantitiesInput!) {
            inventorySetQuantities(input: $input) { userErrors { field message } } }""", {"input": {
            "name": "available", "reason": "correction",
            "quantities": [{"inventoryItemId": pub.ref_inventario, "locationId": self._cred("location_id"),
                            "quantity": cantidad, "changeFromQuantity": None}]}})
        errores = d["inventorySetQuantities"]["userErrors"]
        if errores:
            raise ErrorConector(f"Shopify: {errores}")

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        d = await self._gql("""query($id: ID!) { order(id: $id) { fulfillmentOrders(first: 10) {
            nodes { id status } } } }""", {"id": pedido.pedido_externo})
        abiertas = [f["id"] for f in d["order"]["fulfillmentOrders"]["nodes"] if f["status"] in ("OPEN", "IN_PROGRESS")]
        if not abiertas:
            return None
        r = await self._gql("""mutation($f: FulfillmentInput!) { fulfillmentCreate(fulfillment: $f) {
            fulfillment { id } userErrors { field message } } }""", {"f": {
            "lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": i} for i in abiertas],
            "trackingInfo": {"number": tracking, "company": transportadora}, "notifyCustomer": True}})
        if r["fulfillmentCreate"]["userErrors"]:
            raise ErrorConector(f"Shopify: {r['fulfillmentCreate']['userErrors']}")
        return r["fulfillmentCreate"]["fulfillment"]["id"]

    async def marcar_entregado(self, pedido) -> None:
        if pedido.envio_externo:
            await self._gql("""mutation($e: FulfillmentEventInput!) { fulfillmentEventCreate(fulfillmentEvent: $e) {
                userErrors { message } } }""", {"e": {"fulfillmentId": pedido.envio_externo, "status": "DELIVERED"}})

    def refs_de_webhook(self, cuerpo: Any, encabezados: Dict[str, str]) -> List[str]:
        if isinstance(cuerpo, dict) and cuerpo.get("admin_graphql_api_id"):
            return [cuerpo["admin_graphql_api_id"]]
        return []

    def verificar_firma(self, crudo: bytes, encabezados: Dict[str, str]) -> bool:
        secreto = self.credenciales.get("webhook_secret")
        if not secreto:
            return True
        firma = encabezados.get("x-shopify-hmac-sha256", "")
        calc = base64.b64encode(hmac.new(secreto.encode(), crudo, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(firma, calc)


# ═════════════════════════════════════════════════════════════════════════════
# WooCommerce (REST API v3)
# ═════════════════════════════════════════════════════════════════════════════
class WooCommerce(Adaptador):
    tipo = "WOOCOMMERCE"
    capacidades = Capacidades(notas=[
        "Cree una clave de API REST en WooCommerce › Ajustes › Avanzado › API REST (permisos de lectura y escritura).",
        "La tienda debe estar en HTTPS. Para avisos inmediatos, cree un webhook «Pedido creado» hacia la URL pública del conector.",
    ])

    @property
    def base(self) -> str:
        return (self.config.get("api_base") or self._cred("url")).rstrip("/") + "/wp-json/wc/v3"

    async def _r(self, metodo: str, ruta: str, **kw) -> Any:
        return await self._http(metodo, f"{self.base}{ruta}",
                                auth=(self._cred("consumer_key"), self._cred("consumer_secret")), **kw)

    async def probar(self) -> str:
        await self._r("GET", "/orders", params={"per_page": 1})
        return f"Tienda {self.credenciales.get('url')}"

    def _normalizar(self, o: Dict[str, Any]) -> PedidoNorm:
        b, s = o.get("billing") or {}, o.get("shipping") or {}
        lineas = [LineaNorm(cantidad=num(li.get("quantity"), 0), ref_externa=str(li.get("product_id") or ""),
                            ref_variante=str(li.get("variation_id") or "") if li.get("variation_id") else "",
                            sku=li.get("sku"), titulo=li.get("name"), precio=num(li.get("price")))
                  for li in o.get("line_items") or []]
        estado = o.get("status")
        return PedidoNorm(
            pedido_externo=str(o["id"]), lineas=lineas, estado_externo=estado,
            pagado=estado in ("processing", "completed", "on-hold"), cancelado=estado in ("cancelled", "refunded", "failed"),
            fecha=fecha(o.get("date_created_gmt") or o.get("date_created")),
            comprador=" ".join(x for x in (s.get("first_name") or b.get("first_name"), s.get("last_name") or b.get("last_name")) if x),
            telefono=b.get("phone"), email=b.get("email"),
            direccion=" ".join(x for x in (s.get("address_1"), s.get("address_2")) if x) or None,
            ciudad=s.get("city") or b.get("city"), total=num(o.get("total")), crudo={"id": o["id"], "number": o.get("number")})

    async def pedido(self, ref: str) -> Optional[PedidoNorm]:
        return self._normalizar(await self._r("GET", f"/orders/{ref}"))

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        r = await self._r("GET", "/orders", params={"after": _iso(desde), "per_page": 50, "orderby": "date", "order": "desc"})
        return [self._normalizar(o) for o in r or []]

    async def publicaciones(self) -> List[PublicacionNorm]:
        salida = []
        for pagina in range(1, 21):
            prods = await self._r("GET", "/products", params={"per_page": 100, "page": pagina})
            if not prods:
                break
            for p in prods:
                if p.get("type") == "variable":
                    for v in await self._r("GET", f"/products/{p['id']}/variations", params={"per_page": 100}) or []:
                        salida.append(PublicacionNorm(ref_externa=str(p["id"]), ref_variante=str(v["id"]),
                                                      sku=v.get("sku"), titulo=p.get("name")))
                else:
                    salida.append(PublicacionNorm(ref_externa=str(p["id"]), sku=p.get("sku"), titulo=p.get("name")))
        return salida

    async def publicar_stock(self, pub, cantidad: int) -> None:
        ruta = f"/products/{pub.ref_externa}" + (f"/variations/{pub.ref_variante}" if pub.ref_variante else "")
        await self._r("PUT", ruta, json={"manage_stock": True, "stock_quantity": cantidad})

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        await self._r("POST", f"/orders/{pedido.pedido_externo}/notes", json={
            "note": f"Pedido enviado con {transportadora}. Número de seguimiento: {tracking}", "customer_note": True})
        await self._r("PUT", f"/orders/{pedido.pedido_externo}", json={"status": "completed"})
        return None

    async def marcar_entregado(self, pedido) -> None:
        await self._r("POST", f"/orders/{pedido.pedido_externo}/notes",
                      json={"note": "Pedido entregado al cliente.", "customer_note": True})

    def pedido_de_webhook(self, cuerpo: Any) -> Optional[PedidoNorm]:
        if isinstance(cuerpo, dict) and cuerpo.get("id") and "line_items" in cuerpo:
            return self._normalizar(cuerpo)
        return None

    def verificar_firma(self, crudo: bytes, encabezados: Dict[str, str]) -> bool:
        secreto = self.credenciales.get("webhook_secret")
        if not secreto:
            return True
        firma = encabezados.get("x-wc-webhook-signature", "")
        calc = base64.b64encode(hmac.new(secreto.encode(), crudo, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(firma, calc)


# ═════════════════════════════════════════════════════════════════════════════
# VTEX (OMS + Logistics)
# ═════════════════════════════════════════════════════════════════════════════
class VTEX(Adaptador):
    tipo = "VTEX"
    capacidades = Capacidades(notas=[
        "Use una AppKey/AppToken con permisos de OMS (pedidos) y Logistics (inventario).",
        "El ID de bodega (warehouse) es la bodega de VTEX cuyo inventario se actualiza.",
        "Al despachar se envía la factura de salida con el número de seguimiento (invoice).",
    ])

    @property
    def base(self) -> str:
        return (self.config.get("api_base")
                or f"https://{self._cred('cuenta')}.{self.credenciales.get('entorno') or 'vtexcommercestable'}.com.br").rstrip("/")

    def _h(self) -> Dict[str, str]:
        return {"X-VTEX-API-AppKey": self._cred("app_key"), "X-VTEX-API-AppToken": self._cred("app_token"),
                "Accept": "application/json"}

    async def probar(self) -> str:
        await self._http("GET", f"{self.base}/api/oms/pvt/orders", params={"per_page": 1}, headers=self._h())
        return f"Cuenta {self.credenciales.get('cuenta')}"

    def _normalizar(self, o: Dict[str, Any]) -> PedidoNorm:
        cli = o.get("clientProfileData") or {}
        dir_ = ((o.get("shippingData") or {}).get("address")) or {}
        lineas = [LineaNorm(cantidad=num(i.get("quantity"), 0), ref_externa=str(i.get("id")), sku=i.get("refId"),
                            titulo=i.get("name"), precio=(num(i.get("sellingPrice"), 0) or 0) / 100)
                  for i in o.get("items") or []]
        estado = o.get("status")
        return PedidoNorm(
            pedido_externo=o["orderId"], lineas=lineas, estado_externo=estado,
            pagado=estado in ("ready-for-handling", "handling", "invoiced"), cancelado=estado in ("canceled", "cancellation-requested"),
            fecha=fecha(o.get("creationDate")),
            comprador=" ".join(x for x in (cli.get("firstName"), cli.get("lastName")) if x),
            documento=cli.get("document"), telefono=cli.get("phone"), email=cli.get("email"),
            direccion=" ".join(x for x in (dir_.get("street"), dir_.get("number"), dir_.get("complement")) if x) or None,
            ciudad=dir_.get("city"), total=(num(o.get("value"), 0) or 0) / 100, crudo={"orderId": o["orderId"]})

    async def pedido(self, ref: str) -> Optional[PedidoNorm]:
        return self._normalizar(await self._http("GET", f"{self.base}/api/oms/pvt/orders/{ref}", headers=self._h()))

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        r = await self._http("GET", f"{self.base}/api/oms/pvt/orders", headers=self._h(),
                             params={"f_status": "ready-for-handling", "per_page": 50})
        return [await self.pedido(o["orderId"]) for o in (r or {}).get("list", [])]

    async def publicaciones(self) -> List[PublicacionNorm]:
        ids = await self._http("GET", f"{self.base}/api/catalog_system/pvt/sku/stockkeepingunitids",
                               params={"page": 1, "pagesize": 1000}, headers=self._h()) or []
        salida = []
        for i in ids[:500]:
            s = await self._http("GET", f"{self.base}/api/catalog/pvt/stockkeepingunit/{i}", headers=self._h())
            salida.append(PublicacionNorm(ref_externa=str(i), sku=s.get("RefId"), titulo=s.get("Name")))
        return salida

    async def publicar_stock(self, pub, cantidad: int) -> None:
        await self._http("PUT", f"{self.base}/api/logistics/pvt/inventory/skus/{pub.ref_externa}/warehouses/"
                         f"{self._cred('warehouse_id')}", headers=self._h(),
                         json={"unlimitedQuantity": False, "quantity": cantidad})

    async def confirmar_recepcion(self, pedido) -> None:
        await self._http("POST", f"{self.base}/api/oms/pvt/orders/{pedido.pedido_externo}/start-handling", headers=self._h())

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        factura = tracking
        await self._http("POST", f"{self.base}/api/oms/pvt/orders/{pedido.pedido_externo}/invoice", headers=self._h(), json={
            "type": "Output", "invoiceNumber": factura, "invoiceValue": int(round(float(pedido.total or 0) * 100)),
            "issuanceDate": datetime.now(timezone.utc).date().isoformat(), "trackingNumber": tracking,
            "courier": transportadora})
        return factura

    async def marcar_entregado(self, pedido) -> None:
        if pedido.envio_externo:
            await self._http("PUT", f"{self.base}/api/oms/pvt/orders/{pedido.pedido_externo}/invoice/"
                             f"{pedido.envio_externo}/tracking", headers=self._h(), json={"isDelivered": True})

    def refs_de_webhook(self, cuerpo: Any, encabezados: Dict[str, str]) -> List[str]:
        if isinstance(cuerpo, dict) and cuerpo.get("OrderId"):
            return [cuerpo["OrderId"]]
        return []


# ═════════════════════════════════════════════════════════════════════════════
# Rappi (API de aliados)
# ═════════════════════════════════════════════════════════════════════════════
class Rappi(Adaptador):
    """API de aliados de Rappi (dev-portal.rappi.com). El acceso lo otorga Rappi
    tras una certificación; la entrega la hace el repartidor de Rappi."""
    tipo = "RAPPI"
    capacidades = Capacidades(stock=False, entrega=False, publicaciones=False, notas=[
        "Rappi entrega client_id y client_secret a los aliados después de su certificación de integración.",
        "En Rappi el pedido lo recoge su repartidor: al despachar se marca «listo para recoger» (no usa viaje propio del TMS).",
        "Rappi exige al menos 45 segundos entre consultas; los pedidos también pueden llegar por webhook.",
        "La disponibilidad de productos en Rappi se gestiona en su portal: este conector no la publica todavía.",
    ])

    @property
    def base(self) -> str:
        return (self.config.get("api_base") or self._cred("dominio_pais")).rstrip("/")

    async def _token(self) -> str:
        exp = fecha(self.credenciales.get("expira"))
        if self.credenciales.get("access_token") and exp and exp > datetime.now(timezone.utc):
            return self.credenciales["access_token"]
        r = await self._http("POST", f"{self.base}/restaurants/auth/v1/token/login/integrations",
                             json={"client_id": self._cred("client_id"), "client_secret": self._cred("client_secret")})
        self.credenciales.update({"access_token": r["access_token"],
                                  "expira": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()})
        self.credenciales_cambiaron = True
        return r["access_token"]

    async def _r(self, metodo: str, ruta: str, **kw) -> Any:
        return await self._http(metodo, f"{self.base}/api/v2/restaurants-integrations-public-api{ruta}",
                                headers={"x-authorization": f"Bearer {await self._token()}"}, **kw)

    async def probar(self) -> str:
        await self._token()
        return "Credenciales de aliado válidas"

    def _normalizar(self, o: Dict[str, Any]) -> PedidoNorm:
        det = o.get("order_detail") or o
        cli = det.get("customer") or {}
        dir_ = det.get("delivery_information") or {}
        lineas = [LineaNorm(cantidad=num(i.get("quantity"), 0), ref_externa=str(i.get("id") or ""), sku=i.get("sku"),
                            titulo=i.get("name"), precio=num(i.get("price")))
                  for i in det.get("items") or []]
        return PedidoNorm(
            pedido_externo=str(det.get("order_id") or o.get("id")), lineas=lineas,
            estado_externo=o.get("status") or det.get("status"), pagado=True,
            cancelado=(o.get("status") or "").upper() in ("CANCELED", "REJECTED"),
            fecha=fecha(det.get("created_at")),
            comprador=" ".join(x for x in (cli.get("first_name"), cli.get("last_name")) if x),
            telefono=cli.get("phone_number"), documento=cli.get("document_number"),
            direccion=dir_.get("complete_address") or dir_.get("address"), ciudad=dir_.get("city"),
            total=num(((det.get("totals") or {}).get("total_order"))), crudo=o)

    async def pedidos_recientes(self, desde: datetime) -> List[PedidoNorm]:
        return [self._normalizar(o) for o in await self._r("GET", "/orders") or []]

    async def confirmar_recepcion(self, pedido) -> None:
        await self._r("PUT", f"/orders/{pedido.pedido_externo}/take/{int(self.config.get('minutos_preparacion') or 20)}")

    async def marcar_enviado(self, pedido, tracking: str, transportadora: str) -> Optional[str]:
        await self._r("POST", f"/orders/{pedido.pedido_externo}/ready-for-pickup")
        return None

    def pedido_de_webhook(self, cuerpo: Any) -> Optional[PedidoNorm]:
        if isinstance(cuerpo, dict) and (cuerpo.get("order_detail") or cuerpo.get("items")):
            return self._normalizar(cuerpo)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Webhook genérico y archivo (sin API externa)
# ═════════════════════════════════════════════════════════════════════════════
class Generico(Adaptador):
    """Cualquier sistema que pueda enviar un JSON con el formato estándar."""
    tipo = "WEBHOOK"
    capacidades = Capacidades(pedidos_api=False, stock=False, envio=False, entrega=False, publicaciones=False, notas=[
        "Envíe cada pedido por POST a la URL pública del conector con el formato estándar (ver ejemplo).",
    ])

    async def probar(self) -> str:
        return "Listo para recibir pedidos en la URL pública"

    def pedido_de_webhook(self, cuerpo: Any) -> Optional[PedidoNorm]:
        return normalizar_estandar(cuerpo)


class Archivo(Generico):
    tipo = "ARCHIVO"
    capacidades = Capacidades(pedidos_api=False, stock=False, envio=False, entrega=False, publicaciones=False,
                              webhook=False, notas=["Los pedidos se cargan desde Excel o CSV en «Importar pedidos»."])

    async def probar(self) -> str:
        return "Listo para importar archivos"


def normalizar_estandar(c: Any) -> Optional[PedidoNorm]:
    """Formato estándar de Daily Logistics (webhook genérico y archivos)."""
    if not isinstance(c, dict) or not c.get("pedido"):
        return None
    lineas = [LineaNorm(cantidad=num(l.get("cantidad"), 0), sku=str(l.get("sku") or "").strip() or None,
                        titulo=l.get("titulo") or l.get("descripcion"), precio=num(l.get("precio")))
              for l in c.get("lineas") or []]
    return PedidoNorm(
        pedido_externo=str(c["pedido"]).strip(), lineas=lineas, estado_externo=c.get("estado") or "nuevo",
        pagado=True, cancelado=str(c.get("estado") or "").lower() in ("cancelado", "cancelled"),
        fecha=fecha(c.get("fecha")), comprador=c.get("comprador") or c.get("cliente"), documento=c.get("documento"),
        telefono=c.get("telefono"), email=c.get("email"), direccion=c.get("direccion"), ciudad=c.get("ciudad"),
        total=num(c.get("total")), crudo=c)


ADAPTADORES = {a.tipo: a for a in (MercadoLibre, Shopify, WooCommerce, VTEX, Rappi, Generico, Archivo)}

# Qué credenciales pide cada plataforma (para el formulario del conector).
CAMPOS = {
    "MERCADOLIBRE": [("client_id", "Client ID de la aplicación", False), ("client_secret", "Client secret", True)],
    "SHOPIFY": [("tienda", "Dominio de la tienda (xxxx.myshopify.com)", False), ("access_token", "Admin API access token", True),
                ("location_id", "ID de ubicación (gid://shopify/Location/…)", False),
                ("webhook_secret", "Secreto para verificar webhooks (opcional)", True)],
    "WOOCOMMERCE": [("url", "URL de la tienda (https://…)", False), ("consumer_key", "Consumer key", True),
                    ("consumer_secret", "Consumer secret", True), ("webhook_secret", "Secreto del webhook (opcional)", True)],
    "VTEX": [("cuenta", "Nombre de la cuenta", False), ("entorno", "Entorno (vtexcommercestable)", False),
             ("app_key", "AppKey", True), ("app_token", "AppToken", True), ("warehouse_id", "ID de bodega (warehouse)", False)],
    "RAPPI": [("dominio_pais", "Dominio de la API para su país (lo entrega Rappi)", False), ("client_id", "Client ID", False),
              ("client_secret", "Client secret", True)],
    "WEBHOOK": [],
    "ARCHIVO": [],
}


def adaptador(conector) -> Adaptador:
    clase = ADAPTADORES.get(conector.tipo)
    if not clase:
        raise ErrorConector(f"Tipo de conector desconocido: {conector.tipo}")
    return clase(conector.credenciales or {}, conector.config or {})
