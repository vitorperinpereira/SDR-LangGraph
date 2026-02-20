import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EvolutionService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        instance_id: Optional[str] = None,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._instance_id = instance_id

    @property
    def base_url(self) -> str:
        return self._base_url if self._base_url is not None else settings.EVOLUTION_API_URL

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else settings.EVOLUTION_API_KEY

    @property
    def instance_id(self) -> str:
        return self._instance_id if self._instance_id is not None else settings.CLINIC_ID_PILOT

    @property
    def headers(self) -> Dict[str, str]:
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def _normalize_number(phone: str) -> str:
        return phone.split("@")[0] if "@" in phone else phone

    async def check_connection(self) -> bool:
        if not self.base_url or not self.api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, headers={"apikey": self.api_key})
                return response.status_code < 500
        except Exception as exc:
            logger.error("Evolution connection check failed: %s", exc)
            return False

    async def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.base_url or not self.api_key or not self.instance_id:
            logger.warning("Evolution API not fully configured")
            return None

        url = f"{self.base_url}/{path}/{self.instance_id}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if content:
                    return response.json()
                if hasattr(response, "json"):
                    return response.json()
                return {"ok": True}
            except Exception as exc:
                logger.error("Failed Evolution request (%s): %s", path, exc)
                return None

    async def send_presence(self, phone: str, presence: str = "composing") -> Optional[Dict[str, Any]]:
        number = self._normalize_number(phone)
        payload = {"number": number, "presence": presence}
        return await self._post("chat/sendPresence", payload)

    async def mark_as_read(self, phone: str, message_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        number = self._normalize_number(phone)
        payload: Dict[str, Any] = {"number": number}
        if message_id:
            payload["messageId"] = message_id
        return await self._post("chat/markMessageAsRead", payload)

    async def send_message(self, phone: str, message: str) -> Optional[Dict[str, Any]]:
        if not self.base_url or not self.api_key or not self.instance_id:
            logger.warning("Evolution API not fully configured")
            return None

        number = self._normalize_number(phone)
        payload = {"number": number, "text": message}
        return await self._post("message/sendText", payload)


evolution_service = EvolutionService()
