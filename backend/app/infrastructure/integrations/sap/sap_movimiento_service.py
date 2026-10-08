from typing import Dict
from app.infrastructure.integrations.sap.sap_client import SAPClient


class SAPMovimientoService:
    """Publica movimientos de estibas hacia SAP."""

    SAP_GOODS_MOVEMENT = "/sap/opu/odata/sap/ZMM_GOODSMVT_SRV/GoodsMovementSet"

    def __init__(self):
        self.client = SAPClient()

    async def publicar_movimiento(self, movimiento_data: Dict) -> Dict:
        """Envía un movimiento a SAP como documento de material."""
        payload = self._map_to_sap(movimiento_data)
        return await self.client.post(self.SAP_GOODS_MOVEMENT, payload)

    def _map_to_sap(self, data: Dict) -> Dict:
        return {
            "Bldat": data.get("fecha", ""),
            "Bukrs": "1000",
            "Werks": data.get("centro_sap", ""),
            "Lgort": data.get("almacen_sap", ""),
            "Matnr": data.get("material_sap", ""),
            "Menge": str(data.get("cantidad", 1)),
            "Meins": "UN",
            "Bwart": "501",
        }
