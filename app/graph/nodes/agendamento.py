from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from app.graph.nodes.utils import (
    append_history,
    extract_slot_choice,
    has_objection,
    has_preference,
    latest_user_text,
    objection_response,
)
from app.graph.state import GraphState
from app.graph.tools.calendar import buscar_horarios_disponiveis, criar_evento_agenda


def collect_preferences(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    history = append_history(state, user_text)

    if has_objection(user_text):
        response = objection_response(user_text)
        return {
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
        }

    if not has_preference(user_text):
        response = "Voce prefere manha ou tarde? Se quiser, me diga tambem um dia da semana."
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
        }

    slots = buscar_horarios_disponiveis.invoke({"periodo": user_text, "limit": 2})
    if not isinstance(slots, list) or not slots:
        slots = []

    slot_lines = [f"{index}. {slot['start']}" for index, slot in enumerate(slots, start=1)]
    response = "Encontrei estes horarios disponiveis:\n" + "\n".join(slot_lines) + "\n\nResponda com 1 ou 2."
    return {
        "messages": [AIMessage(content=response)],
        "slots": {"options": slots},
        "last_options": [slot["start"] for slot in slots],
        "stage": "waiting_choice",
        "intent": "agendamento",
        "history": history,
        "output_text": response,
        "tool_outputs": {"buscar_horarios_disponiveis": slots},
    }


def waiting_choice(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    options: List[Dict[str, str]] = state.get("slots", {}).get("options", [])
    history = append_history(state, user_text)

    if has_objection(user_text):
        response = objection_response(user_text)
        return {
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
        }

    if not options:
        response = "Nao encontrei os horarios anteriores. Me diga um novo periodo para eu buscar novamente."
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
        }

    selected_slot = extract_slot_choice(user_text, options)
    if selected_slot:
        response = f"Perfeito! Vou confirmar seu horario em {selected_slot['start']}."
        return {
            "messages": [AIMessage(content=response)],
            "selected_slot": selected_slot,
            "stage": "done",
            "intent": "agendamento",
            "lead_status": "agendamento_solicitado",
            "history": history,
            "output_text": response,
        }

    lowered = user_text.lower()
    if any(term in lowered for term in ["nenhum", "outro", "nao", "não"]):
        response = "Sem problema. Me diga novo periodo ou dia para eu buscar outros horarios."
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
        }

    response = "Nao entendi sua escolha. Responda com 1 ou 2 para confirmar um dos horarios."
    return {
        "messages": [AIMessage(content=response)],
        "stage": "waiting_choice",
        "intent": "agendamento",
        "history": history,
        "output_text": response,
    }


def done(state: GraphState) -> Dict[str, Any]:
    selected_slot = state.get("selected_slot")
    if not selected_slot:
        return {"stage": "done", "intent": "agendamento"}

    # Keep side effects disabled by default because confirmation is handled in webhook flow.
    if not state.get("auto_create_calendar_event"):
        return {"stage": "done", "intent": "agendamento"}

    event_payload = {
        "summary": f"Consulta - {state.get('thread_id', 'lead')}",
        "start_time": selected_slot["start"],
        "end_time": selected_slot["end"],
        "description": "Evento criado pelo agente de agendamento.",
    }
    event_result = criar_evento_agenda.invoke(event_payload)
    tool_outputs = dict(state.get("tool_outputs", {}))
    tool_outputs["criar_evento_agenda"] = event_result
    return {
        "stage": "done",
        "intent": "agendamento",
        "tool_outputs": tool_outputs,
    }


def agendamento_node(state: GraphState) -> Dict[str, Any]:
    stage = state.get("stage")
    if stage == "waiting_choice":
        return waiting_choice(state)
    if stage == "done":
        return done(state)
    return collect_preferences(state)
