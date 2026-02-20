import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.evolution_service import EvolutionService
from app.services.redis_service import RedisService
from app.services.supabase_service import SupabaseService


def test_health_endpoint_returns_200() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_redis_service_debounce_memory_fallback() -> None:
    service = RedisService(redis_url="")
    assert await service.acquire_debounce_lock("phone-5511999999999", ttl_seconds=5) is True
    assert await service.acquire_debounce_lock("phone-5511999999999", ttl_seconds=5) is False


def test_supabase_service_requires_credentials() -> None:
    service = SupabaseService(url="", service_role_key="")
    with pytest.raises(ValueError):
        _ = service.client


@pytest.mark.asyncio
async def test_evolution_service_returns_none_when_not_configured() -> None:
    service = EvolutionService(base_url="", api_key="", instance_id="")
    response = await service.send_message("5511999999999", "Oi")
    assert response is None


@pytest.mark.asyncio
async def test_evolution_service_builds_request_payload(monkeypatch) -> None:
    captured = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"ok": True}

    async def fake_post(self, url, json, headers):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    service = EvolutionService(base_url="https://evo.example", api_key="api-key", instance_id="clinic-1")
    result = await service.send_message("5511999999999@s.whatsapp.net", "Mensagem de teste")

    assert result == {"ok": True}
    assert captured["url"] == "https://evo.example/message/sendText/clinic-1"
    assert captured["json"]["number"] == "5511999999999"
    assert captured["json"]["text"] == "Mensagem de teste"
    assert captured["headers"]["apikey"] == "api-key"
