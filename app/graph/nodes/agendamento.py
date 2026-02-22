import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import settings
from app.graph.nodes.humanization import enforce_humanized_response
from app.graph.nodes.llm import build_chat_model, llm_nodes_enabled
from app.graph.nodes.utils import (
    append_history,
    extract_slot_choice,
    has_objection,
    has_preference,
    latest_ai_text,
    latest_user_text,
    objection_response,
)
from app.graph.prompts import build_prompt_context, get_prompt_bundle, get_prompt_profile
from app.graph.state import GraphState
from app.graph.tools.calendar import buscar_horarios_disponiveis, criar_evento_agenda

logger = logging.getLogger(__name__)


def _format_slot_label(slot_start: str) -> str:
    raw = (slot_start or "").strip()
    if not raw:
        return "horario indisponivel"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m as %H:%M")
    except ValueError:
        return raw


def _format_slot_lines(slots: List[Dict[str, str]]) -> str:
    return "\n".join(
        f"{index}. {_format_slot_label(str(slot.get('start', '')))}" for index, slot in enumerate(slots, start=1)
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _limit_response(text: str, max_lines: int = 5, max_chars: int = 380) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if lines:
        normalized = "\n".join(lines[:max_lines])
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip() + "..."
    return normalized


def _apply_anti_repetition(state: GraphState, response: str, alternate: str) -> str:
    if not settings.PROMPT_ENABLE_ANTI_REPETITION:
        return response

    previous = latest_ai_text(state.get("messages", []))
    if previous and _normalize_text(previous) == _normalize_text(response):
        return alternate
    return response


def _guard_humanization(node_name: str, llm_response: str, fallback: str) -> str:
    if not llm_response:
        return fallback
    guarded, issues = enforce_humanized_response(llm_response, fallback)
    if issues:
        logger.info("humanization_guard_blocked node=%s issues=%s", node_name, ",".join(issues))
    return guarded


def _llm_schedule_response(state: GraphState, user_text: str, slots: List[Dict[str, str]] | None = None) -> Tuple[str, str]:
    context = build_prompt_context(state, current_message=user_text, slots=slots)
    bundle = get_prompt_bundle("agendamento", state, context)
    prompt_profile = bundle["profile"]

    if not llm_nodes_enabled(state):
        return "", prompt_profile

    model = build_chat_model(temperature=0.25)
    try:
        ai_msg = model.invoke(
            [
                SystemMessage(content=bundle["system_prompt"]),
                HumanMessage(content=bundle["user_prompt"]),
            ]
        )
        content = getattr(ai_msg, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip(), prompt_profile
        if content:
            return str(content).strip(), prompt_profile
    except Exception as exc:
        logger.warning("LLM agendamento response failed, using fallback: %s", exc)
    return "", prompt_profile


def _log_turn(state: GraphState, stage: str, intent: str, prompt_profile: str) -> None:
    logger.info(
        "agendamento_turn thread_id=%s stage=%s intent=%s prompt_profile=%s",
        state.get("thread_id", "unknown"),
        stage,
        intent,
        prompt_profile,
    )


def collect_preferences(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    history = append_history(state, user_text)
    prompt_profile = get_prompt_profile(state)

    if has_objection(user_text):
        base_response = objection_response(user_text)
        response = _apply_anti_repetition(
            state,
            base_response,
            "entendi. pra facilitar, me diz de onde vc vem e qual periodo e mais viavel. eu vejo um horario que encaixe melhor e vc decide sem pressa, combinado? prefere manha ou tarde?",
        )
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "tratar_objecao",
        }

    if not has_preference(user_text):
        llm_response, prompt_profile = _llm_schedule_response(state, user_text)
        fallback = "boa. vc prefere manha ou tarde? tem algum dia da semana que fica melhor pra vc?"
        candidate = _guard_humanization("agendamento_collect_preferences", llm_response, fallback)
        response = _apply_anti_repetition(
            state,
            candidate,
            "qual dia fica melhor pra vc? prefere manha ou tarde?",
        )
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "coletar_preferencias_dia_periodo",
        }

    slots = buscar_horarios_disponiveis.invoke({"periodo": user_text, "limit": 2})
    if not isinstance(slots, list):
        slots = []

    llm_response, prompt_profile = _llm_schedule_response(state, user_text, slots)
    if slots:
        fallback = "consegui estes horarios pra vc:\n" + _format_slot_lines(slots) + "\nqual vc prefere? me responde com 1 ou 2."
        stage = "waiting_choice"
    else:
        fallback = "nao consegui horario pra esse periodo. tem algum outro dia da semana que fica melhor pra vc?"
        stage = "collect_preferences"

    candidate = _guard_humanization("agendamento_collect_slots", llm_response, fallback)
    response = _apply_anti_repetition(
        state,
        candidate,
        "vamos tentar em outro dia ou periodo pra achar um horario bom. tem algum que fica mais facil?",
    )
    response = _limit_response(response)

    tool_outputs = dict(state.get("tool_outputs", {}))
    tool_outputs["buscar_horarios_disponiveis"] = slots
    _log_turn(state, stage, "agendamento", prompt_profile)

    return {
        "messages": [AIMessage(content=response)],
        "slots": {"options": slots},
        "last_options": [slot["start"] for slot in slots],
        "stage": stage,
        "intent": "agendamento",
        "history": history,
        "output_text": response,
        "tool_outputs": tool_outputs,
        "prompt_profile": prompt_profile,
        "last_agent_goal": "aguardar_escolha_de_horario" if stage == "waiting_choice" else "coletar_preferencias_dia_periodo",
    }


def waiting_choice(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    options: List[Dict[str, str]] = state.get("slots", {}).get("options", [])
    history = append_history(state, user_text)
    prompt_profile = get_prompt_profile(state)

    if has_objection(user_text):
        response = _apply_anti_repetition(
            state,
            objection_response(user_text),
            "sem problema. me diga um novo dia da semana pra gente encontrar o melhor horario.",
        )
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "tratar_objecao",
        }

    lowered = user_text.lower()
    if any(term in lowered for term in ["cancelar", "remarcar", "remarcacao", "remarcacao"]):
        response = "tudo bem. vamos ajustar. me diz qual periodo ou dia fica melhor e eu vejo as opcoes, pode ser?"
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "coletar_preferencias_dia_periodo",
        }

    if not options:
        response = "perdi a listinha anterior aqui. pode me falar o dia de preferencia de novo rapidinho?"
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "coletar_preferencias_dia_periodo",
        }

    selected_slot = extract_slot_choice(user_text, options)
    if selected_slot:
        llm_response, prompt_profile = _llm_schedule_response(state, user_text, [selected_slot])
        slot_label = _format_slot_label(str(selected_slot.get("start", "")))
        fallback = f"Perfeito! Sua avaliação ficou em {slot_label}. Se precisar reagendar, é só me chamar por aqui."
        candidate = _guard_humanization("agendamento_waiting_choice", llm_response, fallback)
        response = _apply_anti_repetition(
            state,
            candidate,
            f"Perfeito! Sua avaliação ficou em {slot_label}. Se precisar reagendar, é só me chamar por aqui.",
        )
        response = _limit_response(response)
        _log_turn(state, "done", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "selected_slot": selected_slot,
            "stage": "done",
            "intent": "agendamento",
            "lead_status": "agendamento_solicitado",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "confirmar_agendamento",
        }

    if any(term in lowered for term in ["nenhum", "outro", "nao"]):
        response = "sem problema. me diz novo periodo ou dia pra eu buscar os horarios la na agenda."
        response = _limit_response(response)
        _log_turn(state, "collect_preferences", "agendamento", prompt_profile)
        return {
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "intent": "agendamento",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "coletar_preferencias_dia_periodo",
        }

    response = "desculpa, nao entendi qual horario ficou melhor. me responde so com 1 ou 2 pra confirmar?"
    response = _apply_anti_repetition(
        state,
        response,
        "pra ficar mais facil e nao ter erro, manda o numero 1 ou 2, por favor.",
    )
    response = _limit_response(response)
    _log_turn(state, "waiting_choice", "agendamento", prompt_profile)
    return {
        "messages": [AIMessage(content=response)],
        "stage": "waiting_choice",
        "intent": "agendamento",
        "history": history,
        "output_text": response,
        "prompt_profile": prompt_profile,
        "last_agent_goal": "aguardar_escolha_de_horario",
    }


def done(state: GraphState) -> Dict[str, Any]:
    selected_slot = state.get("selected_slot")
    if not selected_slot:
        return {
            "stage": "done",
            "intent": "agendamento",
            "prompt_profile": get_prompt_profile(state),
            "last_agent_goal": "agendamento_concluido",
        }

    # Keep side effects disabled by default because confirmation is handled in webhook flow.
    if not state.get("auto_create_calendar_event"):
        return {
            "stage": "done",
            "intent": "agendamento",
            "prompt_profile": get_prompt_profile(state),
            "last_agent_goal": "agendamento_concluido",
        }

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
        "prompt_profile": get_prompt_profile(state),
        "last_agent_goal": "agendamento_concluido",
    }


def agendamento_node(state: GraphState) -> Dict[str, Any]:
    stage = state.get("stage")
    if stage == "waiting_choice":
        return waiting_choice(state)
    if stage == "done":
        return done(state)
    return collect_preferences(state)

