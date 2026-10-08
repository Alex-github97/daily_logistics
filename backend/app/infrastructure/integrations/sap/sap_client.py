import httpx
from typing import Any, Dict, Optional
from app.core.config import settings


class SAPClient:
    """Cliente base para integración con SAP via OData/REST."""

    def __init__(self):
        self.base_url = f"https://{settings.SAP_HOST}:{settings.SAP_PORT}"
        self.auth = (settings.SAP_USER, settings.SAP_PASSWORD)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "sap-client": settings.SAP_CLIENT,
        }

    async def get(self, path: str, params: Optional[Dict] = None) -> Any:
        if not settings.SAP_ENABLED:
            return {"mock": True, "message": "SAP integration disabled"}
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                auth=self.auth,
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def post(self, path: str, data: Dict) -> Any:
        if not settings.SAP_ENABLED:
            return {"mock": True, "message": "SAP integration disabled"}
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                auth=self.auth,
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()
