import base64
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AudioService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else settings.OPENAI_API_KEY

    @property
    def api_base_url(self) -> str:
        raw = self._api_base_url if self._api_base_url is not None else settings.OPENAI_API_BASE_URL
        return raw.rstrip("/")

    @property
    def model(self) -> str:
        return self._model if self._model is not None else settings.OPENAI_AUDIO_MODEL

    @property
    def timeout_seconds(self) -> int:
        raw = self._timeout_seconds if self._timeout_seconds is not None else settings.OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS
        return max(5, int(raw))

    async def _download_audio(self, audio_url: str) -> Optional[bytes]:
        if not audio_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                return response.content
        except Exception as exc:
            logger.error("Failed to download audio from URL: %s", exc)
            return None

    def _decode_base64_audio(self, audio_base64: str) -> Optional[bytes]:
        if not audio_base64:
            return None
        try:
            return base64.b64decode(audio_base64, validate=False)
        except Exception as exc:
            logger.error("Failed to decode base64 audio: %s", exc)
            return None

    async def transcribe_audio_bytes(self, audio_bytes: bytes, mime_type: str = "audio/ogg", filename: str = "voice.ogg") -> str:
        if not audio_bytes:
            return ""
        if not self.api_key:
            logger.warning("Skipping transcription because OPENAI_API_KEY is not configured.")
            return ""

        endpoint = f"{self.api_base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model}
        files = {"file": (filename, audio_bytes, mime_type)}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, data=payload, files=files)
                response.raise_for_status()
                data = response.json()
                return str(data.get("text", "")).strip()
        except Exception as exc:
            logger.error("Transcription request failed: %s", exc)
            return ""

    async def transcribe(
        self,
        audio_url: Optional[str] = None,
        audio_base64: Optional[str] = None,
        mime_type: str = "audio/ogg",
        filename: str = "voice.ogg",
    ) -> str:
        audio_bytes: Optional[bytes] = None
        if audio_url:
            audio_bytes = await self._download_audio(audio_url)
        elif audio_base64:
            audio_bytes = self._decode_base64_audio(audio_base64)

        if not audio_bytes:
            return ""
        return await self.transcribe_audio_bytes(audio_bytes, mime_type=mime_type, filename=filename)


audio_service = AudioService()

