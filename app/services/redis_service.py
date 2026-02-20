import logging
import time
from typing import Dict, Optional

from redis import asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, redis_url: Optional[str] = None, default_ttl_seconds: Optional[int] = None):
        self._redis_url = redis_url
        self._default_ttl_seconds = default_ttl_seconds
        self._client: Optional[redis.Redis] = None
        self._memory_debounce: Dict[str, float] = {}

    @property
    def redis_url(self) -> str:
        return self._redis_url if self._redis_url is not None else settings.REDIS_URL

    @property
    def default_ttl_seconds(self) -> int:
        raw = self._default_ttl_seconds if self._default_ttl_seconds is not None else settings.REDIS_DEBOUNCE_TTL_SECONDS
        return max(1, int(raw))

    async def _get_client(self) -> Optional[redis.Redis]:
        if not self.redis_url:
            return None
        if self._client is None:
            self._client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        return self._client

    async def check_connection(self) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            await client.ping()
            return True
        except Exception as exc:
            logger.error("Redis connection check failed: %s", exc)
            return False

    def _cleanup_memory(self, now: float) -> None:
        expired_keys = [key for key, expires_at in self._memory_debounce.items() if expires_at <= now]
        for key in expired_keys:
            self._memory_debounce.pop(key, None)

    async def acquire_debounce_lock(self, key: str, ttl_seconds: Optional[int] = None) -> bool:
        ttl = max(1, int(ttl_seconds or self.default_ttl_seconds))
        cache_key = f"debounce:{key}"

        client = await self._get_client()
        if client is not None:
            try:
                was_set = await client.set(cache_key, "1", ex=ttl, nx=True)
                return bool(was_set)
            except Exception as exc:
                logger.warning("Redis debounce failed, using in-memory fallback: %s", exc)

        now = time.monotonic()
        self._cleanup_memory(now)
        if self._memory_debounce.get(cache_key, 0) > now:
            return False
        self._memory_debounce[cache_key] = now + ttl
        return True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


redis_service = RedisService()
