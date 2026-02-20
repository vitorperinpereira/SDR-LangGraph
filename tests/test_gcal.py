import base64
import json

from app import gcal


def test_gcal_setup_from_b64(monkeypatch):
    creds_payload = {"type": "service_account", "client_email": "x@test", "private_key": "-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----\n"}
    encoded = base64.b64encode(json.dumps(creds_payload).encode("utf-8")).decode("utf-8")

    monkeypatch.setattr(gcal.settings, "GCAL_CREDENTIALS_B64", encoded)
    monkeypatch.setattr(gcal.settings, "GCAL_CREDENTIALS_JSON", "credentials.json")

    captured = {}

    def fake_from_info(info, scopes):
        captured["info"] = info
        captured["scopes"] = scopes
        return object()

    def fake_build(service_name, version, credentials):
        captured["build"] = (service_name, version, credentials)
        return object()

    monkeypatch.setattr(gcal.service_account.Credentials, "from_service_account_info", fake_from_info)
    monkeypatch.setattr(gcal, "build", fake_build)

    service = gcal.GCalService()
    assert service.service is not None
    assert captured["info"]["client_email"] == "x@test"
    assert captured["build"][0] == "calendar"


def test_gcal_mock_mode_when_no_credentials(monkeypatch):
    monkeypatch.setattr(gcal.settings, "GCAL_CREDENTIALS_B64", "")
    monkeypatch.setattr(gcal.settings, "GCAL_CREDENTIALS_JSON", "missing.json")
    monkeypatch.setattr(gcal.os.path, "exists", lambda _path: False)

    service = gcal.GCalService()
    result = service.create_event("Consulta", "2026-02-18T10:00:00", "2026-02-18T11:00:00")

    assert service.service is None
    assert result["id"] == "mock_event_id"
