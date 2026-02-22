from fastapi.testclient import TestClient

from app import main


def _monkeypatch_common_dependencies(monkeypatch):
    async def fake_get_or_create_lead(phone, name, clinic_id):
        return {"id": "lead-1", "phone": phone, "name": name, "clinic_id": clinic_id}

    async def fake_get_or_create_conversation(lead_id, clinic_id):
        return {"id": "conv-1", "lead_id": lead_id, "clinic_id": clinic_id}

    async def fake_create_message(*_args, **_kwargs):
        return None

    async def fake_create_appointment(**_kwargs):
        return {"id": "appt-1"}

    async def fake_mark_appointment_confirmed(*_args, **_kwargs):
        return {"id": "appt-1", "status": "confirmed"}

    async def fake_ainvoke(_inputs, config=None):
        _ = config
        return {
            "messages": [type("Msg", (), {"content": "mock"})()],
            "stage": "done",
            "selected_slot": {"start": "2026-02-18T10:00:00", "end": "2026-02-18T11:00:00"},
        }

    async def fake_send_message(_phone, _message):
        return {"ok": True}

    async def fake_mark_as_read(_phone, message_id=None):
        _ = message_id
        return {"ok": True}

    async def fake_send_presence(_phone, presence="composing"):
        _ = presence
        return {"ok": True}

    async def fake_save_followup(**_kwargs):
        return {"id": "follow-1"}

    async def fake_sync_followup(_payload):
        return True

    async def fake_transcribe(**_kwargs):
        return ""

    async def fake_acquire_debounce_lock(_key, ttl_seconds=None):
        _ = ttl_seconds
        return True

    def fake_create_event(*_args, **_kwargs):
        return {"id": "gcal-1", "link": "http://example.com"}

    monkeypatch.setattr(main.db_service, "get_or_create_lead", fake_get_or_create_lead)
    monkeypatch.setattr(main.db_service, "get_or_create_conversation", fake_get_or_create_conversation)
    monkeypatch.setattr(main.db_service, "create_message", fake_create_message)
    monkeypatch.setattr(main.db_service, "create_appointment", fake_create_appointment)
    monkeypatch.setattr(main.db_service, "mark_appointment_confirmed", fake_mark_appointment_confirmed)
    monkeypatch.setattr(main.db_service, "save_followup", fake_save_followup)
    monkeypatch.setattr(main.app_graph, "ainvoke", fake_ainvoke)
    monkeypatch.setattr(main.evolution_service, "send_message", fake_send_message)
    monkeypatch.setattr(main.evolution_service, "mark_as_read", fake_mark_as_read)
    monkeypatch.setattr(main.evolution_service, "send_presence", fake_send_presence)
    monkeypatch.setattr(main.gcal_service, "create_event", fake_create_event)
    monkeypatch.setattr(main.audio_service, "transcribe", fake_transcribe)
    monkeypatch.setattr(main.redis_service, "acquire_debounce_lock", fake_acquire_debounce_lock)


def test_webhook_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(main.settings, "EVOLUTION_WEBHOOK_SECRET", "super-secret")
    client = TestClient(main.app)
    response = client.post("/webhook/evolution", json={"from": "5511999999999", "body": "Oi"})
    assert response.status_code == 401


def test_webhook_processes_simple_payload(monkeypatch):
    monkeypatch.setattr(main.settings, "EVOLUTION_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "CLINIC_ID_PILOT", "clinic-1")
    _monkeypatch_common_dependencies(monkeypatch)

    sent = {}

    async def fake_send_message(phone, message):
        sent["phone"] = phone
        sent["message"] = message
        return {"ok": True}

    monkeypatch.setattr(main.evolution_service, "send_message", fake_send_message)

    client = TestClient(main.app)
    response = client.post("/webhook/evolution", json={"from": "5511999999999", "body": "Oi"})
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert sent["phone"] == "5511999999999@s.whatsapp.net"


def test_webhook_ignores_duplicate_event(monkeypatch):
    monkeypatch.setattr(main.settings, "EVOLUTION_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "CLINIC_ID_PILOT", "clinic-1")
    _monkeypatch_common_dependencies(monkeypatch)
    main._seen_provider_events.clear()

    client = TestClient(main.app)
    payload = {
        "data": {
            "pushName": "Carlos",
            "key": {"id": "evt-1", "remoteJid": "5511999999999@s.whatsapp.net"},
            "message": {"fromMe": False, "conversation": "Oi"},
        }
    }

    first = client.post("/webhook/evolution", json=payload)
    second = client.post("/webhook/evolution", json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "processed"
    assert second.status_code == 200
    assert second.json()["status"] == "ignored_duplicate"


def test_api_webhook_supports_audio_and_sheets_sync(monkeypatch):
    monkeypatch.setattr(main.settings, "EVOLUTION_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "CLINIC_ID_PILOT", "clinic-1")
    _monkeypatch_common_dependencies(monkeypatch)

    captured = {"transcribed": False, "sheet_synced": False, "followup": None}

    async def fake_transcribe(**_kwargs):
        captured["transcribed"] = True
        return "Tenho dor e quero agendar"

    async def fake_ainvoke(_inputs, config=None):
        _ = config
        return {
            "messages": [type("Msg", (), {"content": "mock"})()],
            "stage": "done",
            "intent": "agendamento",
            "interesse": "muito_interesse",
            "chat_resumo": "Lead muito engajado",
            "selected_slot": {"start": "2026-02-18T10:00:00", "end": "2026-02-18T11:00:00"},
        }

    async def fake_save_followup(**kwargs):
        captured["followup"] = kwargs
        return {"id": "follow-1"}

    async def fake_sync_followup(_payload):
        captured["sheet_synced"] = True
        return True

    monkeypatch.setattr(main.audio_service, "transcribe", fake_transcribe)
    monkeypatch.setattr(main.app_graph, "ainvoke", fake_ainvoke)
    monkeypatch.setattr(main.db_service, "save_followup", fake_save_followup)

    client = TestClient(main.app)
    payload = {
        "data": {
            "pushName": "Carlos",
            "key": {"id": "evt-audio-1", "remoteJid": "5511999999999@s.whatsapp.net"},
            "message": {"fromMe": False, "audioMessage": {"url": "https://example.com/audio.ogg"}},
        }
    }
    response = client.post("/api/webhook", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert captured["transcribed"] is True
    assert captured["followup"] is not None
    assert captured["followup"]["interesse"] == "muito_interesse"


def test_api_webhook_ignores_debounced_message(monkeypatch):
    monkeypatch.setattr(main.settings, "EVOLUTION_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "CLINIC_ID_PILOT", "clinic-1")
    _monkeypatch_common_dependencies(monkeypatch)

    async def fake_acquire_debounce_lock(_key, ttl_seconds=None):
        _ = ttl_seconds
        return False

    monkeypatch.setattr(main.redis_service, "acquire_debounce_lock", fake_acquire_debounce_lock)

    client = TestClient(main.app)
    response = client.post("/api/webhook", json={"from": "5511999999999", "body": "Oi"})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored_debounce"


def test_phone_and_text_masking():
    assert main._mask_phone("5511999999999") == "*********9999"
    assert main._mask_text("Meu CPF 12345678900 e telefone 11999999999") == "Meu CPF [num] e telefone [num]"
