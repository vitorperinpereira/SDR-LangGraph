import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graph.nodes.llm import build_chat_model, llm_nodes_enabled
from app.graph.nodes.utils import latest_user_text
from app.graph.prompts import build_prompt_context, get_prompt_bundle
from app.graph.state import GraphState, InteresseLiteral

logger = logging.getLogger(__name__)


def _classify_interesse(state: GraphState) -> InteresseLiteral:
    if state.get("stage") == "done" and state.get("selected_slot"):
        return "muito_interesse"

    user_text = latest_user_text(state.get("messages", [])).lower()
    high_signals = ["quero", "agendar", "horario", "hoje", "amanha"]
    medium_signals = ["talvez", "depois", "ver", "avaliar"]
    low_signals = ["nao", "cancelar", "sem interesse"]

    if any(token in user_text for token in high_signals):
        return "medio_interesse"
    if any(token in user_text for token in medium_signals):
        return "baixo_interesse"
    if any(token in user_text for token in low_signals):
        return "sem_interesse"
    return "baixo_interesse"


def _build_summary(state: GraphState) -> str:
    stage = state.get("stage", "qualify")
    intent = state.get("intent", "unknown")
    selected_slot = state.get("selected_slot")

    if selected_slot:
        summary = (
            f"Lead em fase {stage}, intent={intent}, "
            f"interesse de agendamento com slot escolhido em {selected_slot.get('start')}."
        )
    else:
        summary = (
            f"Lead em fase {stage}, intent={intent}, "
            "sem horario confirmado; sugerido proximo passo de continuidade comercial."
        )
    return summary[:220]


class PostChatAnalysis(BaseModel):
    chat_resumo: str = Field(description="Resumo curto do atendimento em no maximo 220 caracteres.")
    interesse: InteresseLiteral = Field(description="Classificacao final de interesse do lead.")


def _analyze_with_llm(state: GraphState) -> tuple[PostChatAnalysis, str]:
    user_text = latest_user_text(state.get("messages", []))
    context = build_prompt_context(state, current_message=user_text, previous_summary=state.get("chat_resumo", ""))
    bundle = get_prompt_bundle("post_chat", state, context)
    prompt_profile = bundle["profile"]

    if not llm_nodes_enabled(state):
        return PostChatAnalysis(chat_resumo=_build_summary(state), interesse=_classify_interesse(state)), prompt_profile

    model = build_chat_model(temperature=0.1).with_structured_output(PostChatAnalysis)
    try:
        analysis = model.invoke(
            [
                SystemMessage(content=bundle["system_prompt"]),
                HumanMessage(content=bundle["user_prompt"]),
            ]
        )
        return analysis, prompt_profile
    except Exception as exc:
        logger.warning("LLM post-chat analysis failed, using heuristic fallback: %s", exc)
        return PostChatAnalysis(chat_resumo=_build_summary(state), interesse=_classify_interesse(state)), prompt_profile


def interesse_node(state: GraphState) -> Dict[str, Any]:
    analysis, prompt_profile = _analyze_with_llm(state)
    interesse = analysis.interesse
    summary = (analysis.chat_resumo or "").strip()[:220]
    if not summary:
        summary = _build_summary(state)

    lead_status = "qualificado" if interesse in {"muito_interesse", "medio_interesse"} else "em_nutricao"
    logger.info(
        "post_chat_turn thread_id=%s interesse=%s stage=%s intent=%s prompt_profile=%s",
        state.get("thread_id", "unknown"),
        interesse,
        state.get("stage", "qualify"),
        state.get("intent", "unknown"),
        prompt_profile,
    )
    return {
        "chat_resumo": summary,
        "interesse": interesse,
        "lead_status": lead_status,
        "prompt_profile": prompt_profile,
        "last_agent_goal": "sintetizar_resumo_e_interesse",
    }
