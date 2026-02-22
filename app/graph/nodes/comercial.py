import logging
import re
from typing import Any, Dict, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import settings
from app.graph.nodes.humanization import enforce_humanized_response
from app.graph.nodes.llm import build_chat_model, llm_nodes_enabled
from app.graph.nodes.utils import (
    append_history,
    has_objection,
    is_explicit_schedule_request,
    latest_ai_text,
    latest_user_text,
    objection_response,
)
from app.graph.prompts import build_prompt_context, get_prompt_bundle, get_prompt_profile
from app.graph.state import GraphState
from app.graph.tools.kb_retriever import kb_gmv

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _limit_response(text: str, max_lines: int = 5, max_chars: int = 420) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if lines:
        normalized = "\n".join(lines[:max_lines])
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip() + "..."
    return normalized


def _kb_has_context(kb_text: str) -> bool:
    lowered = (kb_text or "").strip().lower()
    if not lowered:
        return False
    failure_markers = [
        "indisponivel",
        "nao encontrei",
        "nao foi possivel",
        "sem trechos uteis",
        "nao recebi pergunta",
    ]
    return not any(marker in lowered for marker in failure_markers)


def _load_kb_context(state: GraphState, user_text: str) -> Tuple[str, bool]:
    try:
        kb_text = kb_gmv.invoke({"query": user_text, "clinic_id": state.get("clinic_id"), "top_k": 3})
    except Exception as exc:
        logger.warning("KB query failed, using fallback context: %s", exc)
        kb_text = "Nao foi possivel consultar a base agora."

    kb_text = str(kb_text or "").strip()
    if not kb_text:
        kb_text = "Nao encontrei artigos relacionados na base."
    return kb_text, _kb_has_context(kb_text)


def _fallback_response(*, user_text: str, kb_text: str, kb_has_context: bool) -> str:
    _ = user_text
    if kb_has_context:
        return (
            "Perfeito, te explico de forma objetiva.\n"
            f"Base de apoio:\n{kb_text}\n\n"
            "Se fizer sentido para voce, eu ja te mostro horarios para avaliacao."
        )
    return (
        "Posso te orientar com o que tenho agora, mas sem inventar detalhes.\n"
        "Para valores exatos e plano ideal, a avaliacao confirma tudo com seguranca.\n"
        "Se quiser, ja te mostro os horarios disponiveis."
    )


def _llm_comercial_response(state: GraphState, user_text: str, kb_text: str) -> Tuple[str, str]:
    context = build_prompt_context(state, current_message=user_text)
    context["slots_context"] = kb_text
    bundle = get_prompt_bundle("comercial", state, context)
    fallback = _fallback_response(user_text=user_text, kb_text=kb_text, kb_has_context=_kb_has_context(kb_text))

    if not llm_nodes_enabled(state):
        return fallback, bundle["profile"]

    model = build_chat_model(temperature=0.3)
    try:
        ai_msg = model.invoke(
            [
                SystemMessage(content=bundle["system_prompt"]),
                HumanMessage(content=bundle["user_prompt"]),
            ]
        )
        content = getattr(ai_msg, "content", "")
        if isinstance(content, str) and content.strip():
            guarded = _guard_humanization("comercial", content.strip(), fallback)
            return guarded, bundle["profile"]
        if content:
            guarded = _guard_humanization("comercial", str(content).strip(), fallback)
            return guarded, bundle["profile"]
    except Exception as exc:
        logger.warning("LLM comercial response failed, using fallback: %s", exc)

    return fallback, bundle["profile"]


def _apply_anti_repetition(state: GraphState, response: str) -> str:
    if not settings.PROMPT_ENABLE_ANTI_REPETITION:
        return response

    previous = latest_ai_text(state.get("messages", []))
    if not previous:
        return response

    if _normalize_text(previous) != _normalize_text(response):
        return response

    return (
        "Entendi. Posso te orientar com calma e sem pressa.\n"
        "Se fizer sentido, eu ja te passo horarios para avaliacao e voce decide com tranquilidade."
    )


def _guard_humanization(node_name: str, llm_response: str, fallback: str) -> str:
    if not llm_response:
        return fallback
    guarded, issues = enforce_humanized_response(llm_response, fallback)
    if issues:
        logger.info("humanization_guard_blocked node=%s issues=%s", node_name, ",".join(issues))
    return guarded


def comercial_node(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    history = append_history(state, user_text)
    prompt_profile = get_prompt_profile(state)

    if not user_text:
        response = "Me conta em uma frase o que voce precisa para eu te orientar melhor."
        return {
            "messages": [AIMessage(content=response)],
            "stage": state.get("stage", "qualify"),
            "intent": "comercial",
            "history": history,
            "output_text": response,
            "prompt_profile": prompt_profile,
            "last_agent_goal": "esclarecer_demanda_comercial",
        }

    kb_text, kb_has_context = _load_kb_context(state, user_text)
    if has_objection(user_text):
        response = (
            f"{objection_response(user_text)} "
            "Se quiser, eu ja te mostro horarios para avaliacao sem compromisso."
        )
        stage = "collect_preferences"
        intent = "agendamento"
        last_goal = "tratar_objecao_e_oferecer_agenda"
    else:
        response, prompt_profile = _llm_comercial_response(state, user_text, kb_text)
        stage = "collect_preferences" if is_explicit_schedule_request(user_text) else state.get("stage", "qualify")
        intent = "agendamento" if stage == "collect_preferences" and is_explicit_schedule_request(user_text) else "comercial"
        last_goal = "conduzir_para_agendamento_sem_pressao"

    response = _limit_response(_apply_anti_repetition(state, response))
    tool_outputs = dict(state.get("tool_outputs", {}))
    tool_outputs["kb_gmv"] = kb_text
    tool_outputs["kb_has_context"] = kb_has_context

    logger.info(
        "comercial_turn thread_id=%s stage=%s intent=%s prompt_profile=%s kb_has_context=%s",
        state.get("thread_id", "unknown"),
        stage,
        intent,
        prompt_profile,
        kb_has_context,
    )

    return {
        "messages": [AIMessage(content=response)],
        "stage": stage,
        "intent": intent,
        "history": history,
        "output_text": response,
        "tool_outputs": tool_outputs,
        "prompt_profile": prompt_profile,
        "last_agent_goal": last_goal,
    }
