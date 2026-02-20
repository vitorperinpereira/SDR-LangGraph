from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app.graph.nodes.utils import append_history, has_name, has_need, has_objection, has_preference, latest_user_text
from app.graph.state import GraphState


class IntentClassification(BaseModel):
    intent: Literal["comercial", "agendamento", "qualify", "unknown"] = Field(
        description="Intencao principal detectada no texto do usuario."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confianca do classificador heuristico.")
    reasoning: str = Field(description="Resumo curto da justificativa.")


def _is_comercial_question(text: str) -> bool:
    lowered = text.lower()
    comercial_terms = [
        "valor",
        "preco",
        "preço",
        "quanto",
        "parcel",
        "tratamento",
        "procedimento",
        "clareamento",
        "implante",
        "faceta",
    ]
    return any(term in lowered for term in comercial_terms)


def _is_slot_or_preference_message(text: str) -> bool:
    lowered = text.lower().strip()
    return has_preference(lowered) or lowered in {"1", "2", "opcao 1", "opcao 2", "opção 1", "opção 2"}


def classify_intent(text: str) -> IntentClassification:
    cleaned = (text or "").strip()
    if not cleaned:
        return IntentClassification(intent="qualify", confidence=0.99, reasoning="Mensagem vazia ou sem contexto.")

    if _is_slot_or_preference_message(cleaned):
        return IntentClassification(intent="agendamento", confidence=0.9, reasoning="Mensagem de disponibilidade/slot.")

    if _is_comercial_question(cleaned):
        return IntentClassification(intent="comercial", confidence=0.82, reasoning="Duvida de natureza comercial.")

    if has_objection(cleaned):
        return IntentClassification(intent="agendamento", confidence=0.86, reasoning="Objecao relacionada ao processo.")

    if has_name(cleaned) and has_need(cleaned):
        return IntentClassification(intent="qualify", confidence=0.88, reasoning="Dados basicos para triagem recebidos.")

    return IntentClassification(intent="qualify", confidence=0.7, reasoning="Sem sinal forte de agenda/comercial.")


def classifier_node(state: GraphState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    user_text = latest_user_text(messages)
    classification = classify_intent(user_text)
    history = append_history(state, user_text)

    base_update: Dict[str, Any] = {
        "intent": classification.intent,
        "intent_confidence": classification.confidence,
        "intent_reasoning": classification.reasoning,
        "history": history,
    }

    if not user_text:
        return {
            **base_update,
            "messages": [AIMessage(content="Oi! Sou a Ana da clinica. Qual seu nome e o que voce precisa hoje?")],
            "stage": "qualify",
            "output_text": "pedido_nome_motivo",
        }

    if has_objection(user_text):
        response = (
            "Entendo a questao financeira. Temos formas de pagamento e parcelamento facilitado. "
            "Podemos seguir para te mostrar os melhores horarios?"
        )
        if "medo" in user_text.lower() or "dor" in user_text.lower():
            response = (
                "Fica tranquilo, nosso foco e conforto e atendimento humanizado. "
                "Posso te oferecer opcoes de horario para avaliacao sem compromisso?"
            )
        return {
            **base_update,
            "messages": [AIMessage(content=response)],
            "objection": user_text,
            "stage": "collect_preferences",
            "output_text": response,
        }

    if has_name(user_text) and has_need(user_text):
        response = "Perfeito. Voce prefere atendimento de manha ou tarde? Tem um dia da semana ideal?"
        return {
            **base_update,
            "messages": [AIMessage(content=response)],
            "stage": "collect_preferences",
            "output_text": response,
        }

    if classification.intent == "comercial":
        return {
            **base_update,
            "stage": state.get("stage", "qualify"),
            "output_text": "rotear_comercial",
        }

    response = "Para te ajudar melhor, me diga seu nome e o motivo da consulta."
    return {
        **base_update,
        "messages": [AIMessage(content=response)],
        "stage": "qualify",
        "output_text": response,
    }


def qualify(state: GraphState) -> Dict[str, Any]:
    # Compatibility alias used by existing tests.
    return classifier_node(state)
