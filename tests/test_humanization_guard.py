from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes import agendamento, classifier, comercial
from app.graph.nodes.classifier import IntentClassification
from app.graph.nodes.humanization import enforce_humanized_response, find_robotic_issues


class _FakeChatModel:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _messages):
        return AIMessage(content=self._content)


def test_find_robotic_issues_detects_formal_phrase_and_markdown_list() -> None:
    text = "Prezado paciente, como assistente virtual posso ajudar.\n1. Informe seu nome\n2. Informe horario"
    issues = find_robotic_issues(text)
    assert "formal_or_robotic_phrase" in issues
    assert "list_or_markdown_format" in issues


def test_find_robotic_issues_detects_multiple_questions() -> None:
    issues = find_robotic_issues("voce prefere manha? e qual dia? posso agendar?")
    assert "multiple_questions" in issues


def test_find_robotic_issues_accepts_short_whatsapp_style() -> None:
    text = "oi, te ajudo sim\nvc prefere manha ou tarde?"
    assert find_robotic_issues(text) == []


def test_enforce_humanized_response_uses_fallback_when_robotic() -> None:
    response, issues = enforce_humanized_response(
        "Atenciosamente, estamos a disposicao para quaisquer esclarecimentos.",
        "oi, me conta rapidinho o que vc precisa",
    )
    assert issues
    assert response == "oi, me conta rapidinho o que vc precisa"


def test_classifier_blocks_robotic_llm_output(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier,
        "classify_intent_with_llm",
        lambda _state, _text: IntentClassification(
            source_label="informacoes",
            intent="qualify",
            confidence=0.9,
            reasoning="teste",
        ),
    )
    monkeypatch.setattr(classifier, "llm_nodes_enabled", lambda _state=None: True)
    monkeypatch.setattr(
        classifier,
        "build_chat_model",
        lambda temperature=0.3: _FakeChatModel(
            "Prezado paciente, como assistente virtual posso auxiliar.\n1. Informe nome\n2. Informe horario"
        ),
    )

    result = classifier.classifier_node({"messages": [HumanMessage(content="oi")]})
    response = result["messages"][-1].content.lower()
    assert "assistente virtual" not in response
    assert "rapidinho" in response


def test_comercial_blocks_robotic_llm_output(monkeypatch) -> None:
    monkeypatch.setattr(comercial, "llm_nodes_enabled", lambda _state=None: True)
    monkeypatch.setattr(
        comercial,
        "build_chat_model",
        lambda temperature=0.3: _FakeChatModel(
            "Atenciosamente, poderia informar o procedimento desejado?\n- item 1\n- item 2"
        ),
    )
    monkeypatch.setattr(comercial, "_load_kb_context", lambda _state, _text: ("contexto de teste", True))

    result = comercial.comercial_node({"messages": [HumanMessage(content="qual o valor?")]})
    response = result["messages"][-1].content.lower()
    assert "atenciosamente" not in response
    assert "perfeito, te explico de forma objetiva" in response


def test_agendamento_blocks_robotic_llm_output(monkeypatch) -> None:
    monkeypatch.setattr(
        agendamento,
        "_llm_schedule_response",
        lambda _state, _text, slots=None: (
            "Prezado cliente, como assistente virtual preciso confirmar duas perguntas.\nQual dia? Qual horario?",
            "v5_1",
        ),
    )

    result = agendamento.collect_preferences({"messages": [HumanMessage(content="quero agendar")]})
    response = result["messages"][-1].content.lower()
    assert "assistente virtual" not in response
    assert "prefere" in response
