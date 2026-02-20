from typing import Any, Dict

from langchain_core.messages import AIMessage

from app.graph.nodes.utils import append_history, latest_user_text
from app.graph.state import GraphState
from app.graph.tools.kb_retriever import kb_gmv


def comercial_node(state: GraphState) -> Dict[str, Any]:
    user_text = latest_user_text(state.get("messages", []))
    history = append_history(state, user_text)

    kb_context = kb_gmv.invoke(
        {
            "query": user_text or "informacoes gerais da clinica",
            "clinic_id": state.get("clinic_id"),
            "top_k": 3,
        }
    )

    response = (
        "Claro! Encontrei informacoes que podem ajudar:\n"
        f"{kb_context}\n\n"
        "Se quiser, eu ja sigo com o agendamento da sua avaliacao."
    )

    return {
        "messages": [AIMessage(content=response)],
        "stage": state.get("stage", "qualify"),
        "lead_status": "comercial_engajado",
        "tool_outputs": {"kb_gmv": kb_context},
        "history": history,
        "output_text": response,
    }
