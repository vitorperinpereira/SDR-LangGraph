import pytest
from langchain_core.messages import HumanMessage

from app.graph import app_graph, collect_preferences, qualify, waiting_choice
from app.graph.nodes.classifier import IntentClassification, classify_intent
from app.graph.tools.calendar import buscar_horarios_disponiveis, criar_evento_agenda
from app.graph.tools.kb_retriever import kb_gmv


def test_classifier_returns_pydantic_schema() -> None:
    result = classify_intent("Qual o preco do clareamento?")
    assert isinstance(result, IntentClassification)
    assert result.intent == "comercial"
    assert 0.0 <= result.confidence <= 1.0


def test_kb_tool_invocation_returns_text() -> None:
    result = kb_gmv.invoke({"query": "formas de pagamento", "top_k": 2})
    assert isinstance(result, str)
    assert result


def test_calendar_tools_invocation(monkeypatch) -> None:
    slots = buscar_horarios_disponiveis.invoke({"periodo": "tarde", "limit": 2})
    assert isinstance(slots, list)
    assert len(slots) <= 2

    def fake_create_event(summary, start_time, end_time, description=""):
        return {
            "id": "gcal-event-1",
            "summary": summary,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
        }

    monkeypatch.setattr("app.graph.tools.calendar.gcal_service.create_event", fake_create_event)
    event = criar_evento_agenda.invoke(
        {
            "summary": "Consulta Teste",
            "start_time": "2026-02-19T15:00:00",
            "end_time": "2026-02-19T16:00:00",
            "description": "Teste",
        }
    )
    assert event["id"] == "gcal-event-1"


def test_legacy_exports_are_kept_for_compatibility() -> None:
    qualify_result = qualify({"messages": [HumanMessage(content="Meu nome e Ana e preciso de consulta")]})
    assert qualify_result["stage"] == "collect_preferences"

    collect_result = collect_preferences({"messages": [HumanMessage(content="Prefiro quinta a tarde")]})
    assert collect_result["stage"] == "waiting_choice"

    options = collect_result["slots"]["options"]
    waiting_result = waiting_choice(
        {
            "messages": [HumanMessage(content="Escolho a opcao 1")],
            "slots": {"options": options},
            "stage": "waiting_choice",
        }
    )
    assert waiting_result["stage"] == "done"


@pytest.mark.asyncio
async def test_workflow_routes_comercial_and_agendamento_paths() -> None:
    config_comercial = {"configurable": {"thread_id": "phase2-commercial"}}
    comercial_result = await app_graph.ainvoke(
        {
            "messages": [HumanMessage(content="Qual o valor da consulta?")],
            "clinic_id": "clinic-1",
            "thread_id": "phase2-commercial",
        },
        config=config_comercial,
    )
    assert comercial_result["intent"] == "comercial"
    assert "chat_resumo" in comercial_result
    assert "interesse" in comercial_result

    config_schedule = {"configurable": {"thread_id": "phase2-schedule"}}
    first = await app_graph.ainvoke(
        {
            "messages": [HumanMessage(content="Meu nome e Carlos e estou com dor")],
            "clinic_id": "clinic-1",
            "thread_id": "phase2-schedule",
        },
        config=config_schedule,
    )
    assert first["stage"] == "collect_preferences"

    second = await app_graph.ainvoke(
        {"messages": [HumanMessage(content="Prefiro quinta a tarde")]},
        config=config_schedule,
    )
    assert second["stage"] == "waiting_choice"

    third = await app_graph.ainvoke(
        {"messages": [HumanMessage(content="1")]},
        config=config_schedule,
    )
    assert third["stage"] == "done"
    assert "chat_resumo" in third
