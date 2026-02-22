from langchain_core.messages import HumanMessage

from app.graph import collect_preferences, qualify, waiting_choice
from app.graph.nodes.utils import has_name, has_objection


def test_qualify_advances_when_name_and_need_are_present():
    state = {"messages": [HumanMessage(content="Oi, meu nome e Carlos e estou com dor de dente.")]}
    result = qualify(state)
    assert result["stage"] == "collect_preferences"


def test_collect_preferences_returns_slots_when_preference_exists():
    state = {"messages": [HumanMessage(content="Prefiro tarde na quinta.")]}
    result = collect_preferences(state)
    assert result["stage"] == "waiting_choice"
    assert len(result["slots"]["options"]) == 2


def test_waiting_choice_confirms_selected_slot():
    options = [
        {"start": "2026-02-18T10:00:00", "end": "2026-02-18T11:00:00"},
        {"start": "2026-02-19T15:00:00", "end": "2026-02-19T16:00:00"},
    ]
    state = {
        "messages": [HumanMessage(content="Escolho a opcao 1.")],
        "slots": {"options": options},
    }
    result = waiting_choice(state)
    assert result["stage"] == "done"
    assert result["selected_slot"]["start"] == options[0]["start"]


def test_waiting_choice_confirmation_does_not_ask_name_again():
    options = [
        {"start": "2026-02-18T10:00:00", "end": "2026-02-18T11:00:00"},
        {"start": "2026-02-19T15:00:00", "end": "2026-02-19T16:00:00"},
    ]
    state = {
        "messages": [HumanMessage(content="1")],
        "slots": {"options": options},
        "use_llm_nodes": False,
    }
    result = waiting_choice(state)
    assert result["stage"] == "done"
    response = result["messages"][-1].content.lower()
    assert "nome completo" not in response
    assert "2026-" not in response


def test_has_name_accepts_name_prefix_format():
    assert has_name("Vitor, preciso de implantes") is True


def test_has_objection_does_not_flag_symptom_only():
    assert has_objection("estou com dor de dente") is False
