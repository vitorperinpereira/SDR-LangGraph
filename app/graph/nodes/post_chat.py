from typing import Any, Dict

from app.graph.nodes.utils import latest_user_text
from app.graph.state import GraphState, InteresseLiteral


def _classify_interesse(state: GraphState) -> InteresseLiteral:
    if state.get("stage") == "done" and state.get("selected_slot"):
        return "muito_interesse"

    user_text = latest_user_text(state.get("messages", [])).lower()
    high_signals = ["quero", "agendar", "horario", "hoje", "amanha", "amanhã"]
    medium_signals = ["talvez", "depois", "ver", "avaliar"]
    low_signals = ["nao", "não", "cancelar", "sem interesse"]

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
        return f"Lead em fase {stage}, intent={intent}, slot escolhido={selected_slot.get('start')}."
    return f"Lead em fase {stage}, intent={intent}, sem slot confirmado."


def interesse_node(state: GraphState) -> Dict[str, Any]:
    interesse = _classify_interesse(state)
    summary = _build_summary(state)
    return {
        "chat_resumo": summary,
        "interesse": interesse,
        "lead_status": "qualificado" if interesse in {"muito_interesse", "medio_interesse"} else "em_nutricao",
    }
