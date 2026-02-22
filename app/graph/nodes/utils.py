import re
import unicodedata
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.graph.state import GraphState


def _normalized_lower(text: str) -> str:
    raw = (text or "").strip().lower()
    normalized = unicodedata.normalize("NFD", raw)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def latest_user_text(messages: List[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content.strip()
    return ""


def latest_ai_text(messages: List[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()
            if content:
                return str(content).strip()
    return ""


def has_name(text: str) -> bool:
    lowered = _normalized_lower(text)
    if "meu nome" in lowered or "sou " in lowered:
        return True

    # Accept common conversational pattern like: "Vitor, preciso de implantes"
    # including lowercase and no-space variants: "vitor,implante".
    first_token_match = re.match(r"^\s*([A-Za-zÀ-ÿ]{2,24})\s*,", (text or "").strip())
    if first_token_match:
        token = _normalized_lower(first_token_match.group(1))
        non_name_tokens = {"oi", "ola", "opa", "eai", "bom", "boa", "hello", "hey"}
        if token not in non_name_tokens:
            return True
    return False


def has_need(text: str) -> bool:
    lowered = _normalized_lower(text)
    keywords = [
        "dor",
        "limpeza",
        "avaliacao",
        "canal",
        "aparelho",
        "clareamento",
        "consulta",
        "implante",
        "implantes",
        "faceta",
        "facetas",
        "tratamento",
        "protese",
    ]
    return any(word in lowered for word in keywords)


def has_preference(text: str) -> bool:
    lowered = _normalized_lower(text)
    weekdays = [
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "manha",
        "tarde",
    ]
    return any(word in lowered for word in weekdays)


def is_explicit_schedule_request(text: str) -> bool:
    lowered = _normalized_lower(text)
    explicit_terms = [
        "agendar",
        "agendamento",
        "marcar",
        "horario",
        "data",
        "remarcar",
        "cancelar",
        "confirmo",
        "confirmar",
    ]
    if any(term in lowered for term in explicit_terms):
        return True
    if has_preference(lowered):
        return True
    if re.search(r"\b(1|2)\b", lowered):
        return True
    return False


def is_troll(text: str) -> bool:
    lowered = _normalized_lower(text)
    keywords = ["puta", "caralho", "foda", "merda", "cu ", "palmeiras", "corinthians", "flamengo", "bolsonaro", "lula", "jogo", "troll"]
    # We could make it more sophisticated, but this serves as the "anti-troll / off-topic" MVP logic.
    return any(word in lowered for word in keywords)

def has_objection(text: str) -> bool:
    lowered = _normalized_lower(text)
    keywords = [
        "caro",
        "medo",
        "longe",
        "dificil",
        "nao quero",
        "cancelar",
        "pensar",
        "marido",
        "esposa",
        "tempo",
        "depois",
        "mais tarde",
        "corrido",
        "ver com",
    ]
    return any(word in lowered for word in keywords)


def objection_response(text: str) -> str:
    lowered = _normalized_lower(text)
    if "caro" in lowered or "preco" in lowered or "valor" in lowered:
        return (
            "Entendo a questao financeira. Temos formas de pagamento e parcelamento facilitado. "
            "Podemos seguir para te mostrar os melhores horarios?"
        )
    if "medo" in lowered or "dor" in lowered:
        return (
            "Fica tranquilo, nosso foco e conforto e atendimento humanizado. "
            "Posso te oferecer opcoes de horario para avaliacao sem compromisso?"
        )
    if any(word in lowered for word in ["tempo", "corrido", "depois", "mais tarde", "pensar", "marido", "esposa", "ver com"]):
        return (
            "Claro, sem problemas! Sei que essas decisões precisam de tempo e a rotina é corrida. "
            "Se quiser, posso deixar um horário pré-agendado só para garantir, e você confirma depois. O que acha?"
        )
    return (
        "Entendo sua preocupacao e quero te ajudar com calma. "
        "Posso te mostrar horarios para avaliacao e voce decide sem pressa."
    )


def extract_slot_choice(text: str, options: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    lowered = _normalized_lower(text)
    if lowered in {"1", "opcao 1", "primeira", "primeiro"} and len(options) >= 1:
        return options[0]
    if lowered in {"2", "opcao 2", "segunda", "segundo"} and len(options) >= 2:
        return options[1]

    match = re.search(r"\b([12])\b", lowered)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(options):
            return options[index]

    for slot in options:
        if slot["start"][:16].lower() in lowered:
            return slot
    return None


def append_history(state: GraphState, user_text: str) -> List[str]:
    history = list(state.get("history", []))
    if user_text:
        history.append(user_text)
    return history
