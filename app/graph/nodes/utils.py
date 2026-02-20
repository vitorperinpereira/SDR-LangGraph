import re
from typing import Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage

from app.graph.state import GraphState


def latest_user_text(messages: List[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content.strip()
    return ""


def has_name(text: str) -> bool:
    lowered = text.lower()
    return "meu nome" in lowered or "sou " in lowered


def has_need(text: str) -> bool:
    lowered = text.lower()
    keywords = ["dor", "limpeza", "avaliacao", "avalia", "canal", "aparelho", "clareamento", "consulta"]
    return any(word in lowered for word in keywords)


def has_preference(text: str) -> bool:
    lowered = text.lower()
    weekdays = [
        "segunda",
        "terca",
        "terca-feira",
        "terça",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "sábado",
        "manha",
        "manhã",
        "tarde",
    ]
    return any(word in lowered for word in weekdays)


def has_objection(text: str) -> bool:
    lowered = text.lower()
    keywords = ["caro", "medo", "dor", "longe", "dificil", "difícil", "nao quero", "não quero", "cancelar"]
    return any(word in lowered for word in keywords)


def objection_response(text: str) -> str:
    lowered = text.lower()
    if "caro" in lowered or "preco" in lowered or "preço" in lowered or "valor" in lowered:
        return (
            "Entendo a questao financeira. Temos formas de pagamento e parcelamento facilitado. "
            "Podemos seguir para te mostrar os melhores horarios?"
        )
    if "medo" in lowered or "dor" in lowered:
        return (
            "Fica tranquilo, nosso foco e conforto e atendimento humanizado. "
            "Posso te oferecer opcoes de horario para avaliacao sem compromisso?"
        )
    return (
        "Entendo sua preocupacao e quero te ajudar com calma. "
        "Posso te mostrar horarios para avaliacao e voce decide sem pressa."
    )


def extract_slot_choice(text: str, options: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    lowered = text.lower().strip()
    if lowered in {"1", "opcao 1", "opção 1", "primeira", "primeiro"} and len(options) >= 1:
        return options[0]
    if lowered in {"2", "opcao 2", "opção 2", "segunda", "segundo"} and len(options) >= 2:
        return options[1]

    match = re.search(r"\b([12])\b", lowered)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(options):
            return options[index]

    for slot in options:
        if slot["start"][:16] in lowered:
            return slot
    return None


def append_history(state: GraphState, user_text: str) -> List[str]:
    history = list(state.get("history", []))
    if user_text:
        history.append(user_text)
    return history
