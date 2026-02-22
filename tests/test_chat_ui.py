from fastapi.testclient import TestClient

from app import main


def test_chat_page_loads():
    client = TestClient(main.app)
    response = client.get("/chat")
    assert response.status_code == 200
    assert "Teste o Agente em Tempo Real" in response.text
    assert "/api/chat/test" in response.text


def test_chat_test_endpoint_returns_graph_response(monkeypatch):
    async def fake_ainvoke(_inputs, config=None):
        _ = config
        return {
            "messages": [type("Msg", (), {"content": "Resposta simulada"})()],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "interesse": "medio_interesse",
        }

    monkeypatch.setattr(main.app_graph, "ainvoke", fake_ainvoke)

    client = TestClient(main.app)
    response = client.post(
        "/api/chat/test",
        json={
            "message": "Oi",
            "thread_id": "thread-test-1",
            "clinic_id": "clinic-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "thread-test-1"
    assert body["response"] == "Resposta simulada"
    assert body["stage"] == "collect_preferences"
    assert body["intent"] == "agendamento"
    assert body["interesse"] == "medio_interesse"
    assert "prompt_profile" in body
