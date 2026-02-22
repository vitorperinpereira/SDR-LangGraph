import os
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import settings
from app.graph.state import GraphState


def llm_nodes_enabled(state: Optional[GraphState] = None) -> bool:
    if state and "use_llm_nodes" in state:
        return bool(state.get("use_llm_nodes")) and bool(settings.OPENAI_API_KEY)

    if not settings.OPENAI_USE_LLM_NODES:
        return False
    if not settings.OPENAI_API_KEY:
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return True


def build_chat_model(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=temperature,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE_URL,
    )
