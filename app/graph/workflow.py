import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.config import settings
from app.graph.nodes.agendamento import agendamento_node
from app.graph.nodes.classifier import classifier_node
from app.graph.nodes.comercial import comercial_node
from app.graph.nodes.post_chat import interesse_node
from app.graph.state import GraphState

logger = logging.getLogger(__name__)

workflow = StateGraph(GraphState)
workflow.add_node("classifier", classifier_node)
workflow.add_node("comercial", comercial_node)
workflow.add_node("agendamento", agendamento_node)
workflow.add_node("interesse", interesse_node)


def entry_router(state: GraphState) -> str:
    stage = state.get("stage")
    if stage in {"collect_preferences", "waiting_choice", "done"}:
        return "agendamento"
    return "classifier"


workflow.set_conditional_entry_point(
    entry_router,
    {
        "classifier": "classifier",
        "agendamento": "agendamento",
    },
)


def classifier_router(state: GraphState) -> str:
    if state.get("intent") == "comercial":
        return "comercial"
    return "end"


workflow.add_conditional_edges(
    "classifier",
    classifier_router,
    {
        "comercial": "comercial",
        "end": END,
    },
)


def agendamento_router(state: GraphState) -> str:
    if state.get("stage") == "done":
        return "interesse"
    return "end"


workflow.add_conditional_edges(
    "agendamento",
    agendamento_router,
    {
        "interesse": "interesse",
        "end": END,
    },
)

workflow.add_edge("comercial", "interesse")
workflow.add_edge("interesse", END)

if settings.DATABASE_URL:
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        checkpointer = PostgresSaver.from_conn_string(settings.DATABASE_URL)
    except Exception as exc:
        logger.warning("Falling back to in-memory checkpointer: %s", exc)
        checkpointer = MemorySaver()
else:
    checkpointer = MemorySaver()

app_graph = workflow.compile(checkpointer=checkpointer)


def draw_workflow_png() -> bytes:
    return app_graph.get_graph().draw_mermaid_png()
