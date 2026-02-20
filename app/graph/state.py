import operator
from typing import Annotated, Any, Dict, List, Literal, TypedDict

from langchain_core.messages import BaseMessage

StageLiteral = Literal["qualify", "collect_preferences", "waiting_choice", "done"]
IntentLiteral = Literal["comercial", "agendamento", "qualify", "unknown"]
InteresseLiteral = Literal["muito_interesse", "medio_interesse", "baixo_interesse", "sem_interesse"]


class GraphState(TypedDict, total=False):
    clinic_id: str
    thread_id: str
    stage: StageLiteral
    lead_status: str
    intent: IntentLiteral
    intent_confidence: float
    intent_reasoning: str
    slots: Dict[str, Any]
    last_options: List[str]
    selected_slot: Dict[str, str]
    objection: str
    history: List[str]
    chat_resumo: str
    interesse: InteresseLiteral
    output_text: str
    tool_outputs: Dict[str, Any]
    messages: Annotated[List[BaseMessage], operator.add]
