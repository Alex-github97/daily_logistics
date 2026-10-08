from typing import List, Dict, Optional
from app.infrastructure.integrations.sap.sap_client import SAPClient


class SAPProveedorService:
    """Sincroniza proveedores desde SAP como sistema maestro."""

    SAP_VENDOR_ODATA = "/sap/opu/odata/sap/ZMM_VENDORS_SRV/VendorSet"

    def __init__(self):
        self.client = SAPClient()

    async def get_proveedor(self, codigo_sap: str) -> Optional[Dict]:
        """Obtiene datos de un proveedor desde SAP."""
        path = f"{self.SAP_VENDOR_ODATA}('{codigo_sap}')"
        result = await self.client.get(path)
        return self._map_sap_to_local(result.get("d", {}))

    async def buscar_proveedores(self, nombre: Optional[str] = None) -> List[Dict]:
        """Busca proveedores en SAP."""
        params = {"$format": "json", "$top": 50}
        if nombre:
            params["$filter"] = f"contains(Name1,'{nombre}')"
        result = await self.client.get(self.SAP_VENDOR_ODATA, params=params)
        results = result.get("d", {}).get("results", [])
        return [self._map_sap_to_local(r) for r in results]

    def _map_sap_to_local(self, sap_data: Dict) -> Dict:
        return {
            "codigo_sap": sap_data.get("Lifnr", ""),
            "razon_social": sap_data.get("Name1", ""),
            "nombre_comercial": sap_data.get("Name2", ""),
            "nit": sap_data.get("Stcd1", ""),
            "ciudad": sap_data.get("Ort01", ""),
            "direccion": sap_data.get("Stras", ""),
        }
