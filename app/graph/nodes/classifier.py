import logging
from datetime import datetime
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graph.nodes.humanization import enforce_humanized_response
from app.graph.nodes.llm import build_chat_model, llm_nodes_enabled
from app.graph.nodes.utils import (
    append_history,
    has_name,
    has_need,
    has_objection,
    is_explicit_schedule_request,
    is_troll,
    latest_user_text,
    objection_response,
)
from app.graph.prompts import build_prompt_context, get_prompt_bundle, get_prompt_profile
from app.graph.state import GraphState

logger = logging.getLogger(__name__)


class IntentClassification(BaseModel):
    source_label: Literal["informacoes", "agendamentos"] = Field(
        description="Categoria equivalente ao roteamento do n8n."
    )
    intent: Literal["comercial", "agendamento", "qualify", "unknown"] = Field(
        description="Intencao principal no schema interno do LangGraph."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confianca da classificacao.")
    reasoning: str = Field(description="Resumo curto da justificativa.")


def _is_comercial_question(text: str) -> bool:
    lowered = text.lower()
    comercial_terms = [
        "valor",
        "preco",
        "preco",
        "quanto",
        "parcel",
        "tratamento",
        "procedimento",
        "clareamento",
        "implante",
        "faceta",
    ]
    return any(term in lowered for term in comercial_terms)


def _normalize_classification(text: str, classification: IntentClassification) -> IntentClassification:
    explicit_schedule = is_explicit_schedule_request(text or "")
    source_label = classification.source_label
    intent = classification.intent
    confidence = classification.confidence
    reasoning = classification.reasoning

    if explicit_schedule:
        source_label = "agendamentos"
        intent = "agendamento"
        confidence = max(confidence, 0.9)
        reasoning = "Pedido explicito de agenda detectado."
    elif source_label == "agendamentos":
        intent = "agendamento"
    elif source_label == "informacoes" and intent not in {"comercial", "qualify"}:
        intent = "qualify"

    return IntentClassification(
        source_label=source_label,
        intent=intent,
        confidence=confidence,
        reasoning=reasoning,
    )


def classify_intent(text: str) -> IntentClassification:
    cleaned = (text or "").strip()
    if not cleaned:
        return IntentClassification(
            source_label="informacoes",
            intent="qualify",
            confidence=0.99,
            reasoning="Mensagem vazia ou sem contexto.",
        )

    if is_explicit_schedule_request(cleaned):
        return IntentClassification(
            source_label="agendamentos",
            intent="agendamento",
            confidence=0.9,
            reasoning="Mensagem de disponibilidade, agenda ou horario.",
        )

    if _is_comercial_question(cleaned):
        return IntentClassification(
            source_label="informacoes",
            intent="comercial",
            confidence=0.82,
            reasoning="Duvida de natureza comercial.",
        )

    if has_objection(cleaned):
        return IntentClassification(
            source_label="informacoes",
            intent="comercial",
            confidence=0.78,
            reasoning="Objecao relacionada ao processo.",
        )

    if has_name(cleaned) and has_need(cleaned):
        return IntentClassification(
            source_label="informacoes",
            intent="qualify",
            confidence=0.88,
            reasoning="Dados basicos para triagem recebidos.",
        )

    return IntentClassification(
        source_label="informacoes",
        intent="qualify",
        confidence=0.7,
        reasoning="Sem sinal forte de agenda/comercial.",
    )


def classify_intent_with_llm(state: GraphState, text: str) -> IntentClassification:
    if not llm_nodes_enabled(state):
        return _normalize_classification(text, classify_intent(text))

    model = build_chat_model(temperature=0.0).with_structured_output(IntentClassification)
    context = build_prompt_context(state, current_message=text)
    prompt_bundle = get_prompt_bundle("recepcionista", state, context)

    try:
        raw = model.invoke(
            [
                SystemMessage(content=prompt_bundle["system_prompt"]),
                HumanMessage(content=prompt_bundle["user_prompt"]),
            ]
        )
        return _normalize_classification(text, raw)
    except Exception as exc:
        logger.warning("LLM classification failed, using heuristic fallback: %s", exc)
        return _normalize_classification(text, classify_intent(text))


def _llm_qualify_response(state: GraphState, user_text: str) -> str:
    fallback = "pra te ajudar melhor, me conta rapidinho o que vc quer resolver"
    if not llm_nodes_enabled(state):
        return fallback

    context = build_prompt_context(state, current_message=user_text)
    prompt_bundle = get_prompt_bundle("qualify", state, context)
    model = build_chat_model(temperature=0.3)

    try:
        raw = model.invoke(
            [
                SystemMessage(content=prompt_bundle["system_prompt"]),
                HumanMessage(content=prompt_bundle["user_prompt"]),
            ]
        )
        content = getattr(raw, "content", "")
        if isinstance(content, str) and content.strip():
            guarded, issues = enforce_humanized_response(content.strip(), fallback)
            if issues:
                logger.info("humanization_guard_blocked node=qualify issues=%s", ",".join(issues))
            return guarded
        if content:
            guarded, issues = enforce_humanized_response(str(content).strip(), fallback)
            if issues:
                logger.info("humanization_guard_blocked node=qualify issues=%s", ",".join(issues))
            return guarded
    except Exception as exc:
        logger.warning("LLM qualify response failed, using fallback: %s", exc)

    return fallback


def _format_slot_time(slot_start: str) -> str:
    raw = (slot_start or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%H:%M")
    except ValueError:
        if "T" in raw:
            maybe_time = raw.split("T", 1)[1][:5]
            if len(maybe_time) == 5:
                return maybe_time
        return raw


def _get_availability_suggestion() -> str:
    from app.graph.tools.calendar import buscar_horarios_disponiveis
    try:
        slots = buscar_horarios_disponiveis.invoke({"periodo": "livre", "limit": 2})
        if len(slots) >= 2:
            s1 = _format_slot_time(str(slots[0].get("start", "")))
            s2 = _format_slot_time(str(slots[1].get("start", "")))
            if not (s1 and s2):
                raise ValueError("invalid slot start time")
            return f"quer que eu ja reserve um horario pra vc? tenho vagas hoje as {s1} ou amanha as {s2}"
    except Exception as exc:
        logger.warning("Falha ao buscar availability suggestion: %s", exc)
    return "boa, vc prefere manha ou tarde? tem algum dia da semana que fica melhor pra vc?"

def classifier_node(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    classification = classify_intent_with_llm(state, user_text)
    previous_history = list(state.get("history", []))
    history = append_history(state, user_text)
    prompt_profile = get_prompt_profile(state)

    base_update: Dict[str, Any] = {
        "intent": classification.intent,
        "source_label": classification.source_label,
        "intent_confidence": classification.confidence,
        "intent_reasoning": classification.reasoning,
        "last_user_intent_raw": f"{classification.source_label}:{classification.intent}",
        "prompt_profile": prompt_profile,
        "history": history,
    }

    logger.info(
        "classifier_decision thread_id=%s stage=%s intent=%s source_label=%s prompt_profile=%s",
        state.get("thread_id", "unknown"),
        state.get("stage", "qualify"),
        classification.intent,
        classification.source_label,
        prompt_profile,
    )

    if not user_text:
        return {
            **base_update,
            "messages": [AIMessage(content="oi! eu sou a Athena da clinica. como posso te ajudar? qual seu nome?")],
            "stage": "qualify",
            "last_agent_goal": "coletar_nome_motivo",
            "output_text": "pedido_nome_motivo",
        }

    if is_troll(user_text):
        response = "vamos manter o respeito e o foco. como posso te ajudar com tratamentos na clinica?"
        return {
            **base_update,
            "messages": [AIMessage(content=response)],
            "stage": "qualify",
            "last_agent_goal": "tratar_off_topic",
            "output_text": response,
        }

    if has_objection(user_text):
        response = objection_response(user_text)
        return {
            **base_update,
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "last_agent_goal": "tratar_objecao",
            "output_text": response,
        }

    if classification.intent == "agendamento":
        response = _get_availability_suggestion()
        return {
            **base_update,
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "last_agent_goal": "coletar_preferencia_agenda",
            "output_text": response,
        }

    has_name_now = has_name(user_text)
    has_need_now = has_need(user_text)
    has_name_before = any(has_name(entry) for entry in previous_history)
    has_need_before = any(has_need(entry) for entry in previous_history)
    has_enough_qualification_context = (has_name_now or has_name_before) and (has_need_now or has_need_before)

    if has_enough_qualification_context:
        response = _get_availability_suggestion()
        return {
            **base_update,
            "intent": "agendamento",
            "intent_reasoning": "Nome e necessidade identificados no contexto; seguir para agendamento.",
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "last_agent_goal": "coletar_preferencia_agenda",
            "output_text": response,
        }

    if classification.intent == "comercial":
        return {
            **base_update,
            "stage": state.get("stage", "qualify"),
            "last_agent_goal": "rotear_comercial",
            "output_text": "rotear_comercial",
        }

    response = _llm_qualify_response(state, user_text)
    return {
        **base_update,
        "messages": [AIMessage(content=response)],
        "stage": "qualify",
        "last_agent_goal": "coletar_nome_motivo",
        "output_text": response,
    }


def qualify(state: GraphState) -> Dict[str, Any]:
    # Compatibility alias used by existing tests.
    return classifier_node(state)

