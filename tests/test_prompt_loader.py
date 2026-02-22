from app.graph.prompts import build_prompt_context, get_prompt_bundle


def test_prompt_loader_uses_profile_and_shared_voice() -> None:
    state = {
        "prompt_profile": "v5_1",
        "clinic_id": "clinic-1",
        "thread_id": "thread-1",
        "history": ["Oi", "Quero implante"],
    }
    context = build_prompt_context(state, current_message="Qual o valor?")
    bundle = get_prompt_bundle("comercial", state, context)

    assert bundle["profile"] == "v5_1"
    assert "Athena" in bundle["system_prompt"]
    assert "Qual o valor?" in bundle["user_prompt"]


def test_prompt_loader_fallback_when_profile_missing() -> None:
    state = {
        "prompt_profile": "profile_inexistente",
        "clinic_id": "clinic-1",
        "thread_id": "thread-1",
    }
    context = build_prompt_context(state, current_message="Quero horario")
    bundle = get_prompt_bundle("agendamento", state, context)

    assert bundle["profile"] == "profile_inexistente"
    assert bundle["system_prompt"]
    assert bundle["user_prompt"]
