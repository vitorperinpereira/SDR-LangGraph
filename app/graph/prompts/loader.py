import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from app.config import settings
from app.graph.state import GraphState

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_CACHE: Dict[str, Any] = {}


class PromptContext(TypedDict, total=False):
    current_message: str
    history_window: str
    lead_context: str
    time_context: str
    slots_context: str
    previous_summary: str
    last_agent_goal: str
    last_user_intent_raw: str


class PromptBundle(TypedDict):
    profile: str
    system_prompt: str
    user_prompt: str


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


_FALLBACK_SHARED_VOICE = (
    "Voce e Athena, assistente do GMV. "
    "Mantenha um tom humano, claro, profissional e acolhedor. "
    "Nunca mencione troca de setor, time ou funcao."
)

_FALLBACK_PROMPTS: Dict[str, Tuple[str, str]] = {
    "recepcionista": (
        "Classifique a intencao da mensagem sem responder ao lead. "
        "Use source_label informacoes/agendamentos e mapear para intent.",
        (
            "Mensagem atual:\n{current_message}\n\n"
            "Historico:\n{history_window}\n\n"
            "Contexto:\n{lead_context}\n{time_context}\n\n"
            "Retorne classificacao objetiva."
        ),
    ),
    "comercial": (
        "Responda como Athena de forma humanizada. "
        "Use o contexto da base, sem inventar dados, no maximo 5 linhas.",
        (
            "Lead:\n{lead_context}\n\n"
            "Resumo previo:\n{previous_summary}\n\n"
            "Historico:\n{history_window}\n\n"
            "Pergunta atual:\n{current_message}\n\n"
            "Contexto RAG:\n{slots_context}\n"
        ),
    ),
    "agendamento": (
        "Voce organiza agenda de forma objetiva, cordial e sem perder a continuidade de Athena.",
        (
            "Lead:\n{lead_context}\n\n"
            "Historico:\n{history_window}\n\n"
            "Mensagem atual:\n{current_message}\n\n"
            "Opcoes de horario:\n{slots_context}\n\n"
            "Ultimo objetivo do agente:\n{last_agent_goal}\n"
        ),
    ),
    "post_chat": (
        "Analise o historico e gere chat_resumo curto e interesse sem conversar com o lead.",
        (
            "Lead:\n{lead_context}\n\n"
            "Historico:\n{history_window}\n\n"
            "Mensagem atual:\n{current_message}\n\n"
            "Resumo anterior:\n{previous_summary}\n"
        ),
    ),
}


def get_prompt_profile(state: Optional[GraphState] = None) -> str:
    if state and state.get("prompt_profile"):
        return str(state.get("prompt_profile"))
    return settings.PROMPT_PROFILE


def _history_window_text(state: GraphState) -> str:
    history = list(state.get("history", []))
    max_items = max(1, int(settings.PROMPT_MAX_HISTORY_MESSAGES))
    clipped = history[-max_items:]
    if not clipped:
        return "sem historico"
    return "\n".join(f"- {item}" for item in clipped)


def _slots_context_text(slots: Optional[List[Dict[str, Any]]] = None) -> str:
    if not slots:
        return "sem opcoes de horario"
    lines: List[str] = []
    for idx, slot in enumerate(slots, start=1):
        start = str(slot.get("start", ""))
        end = str(slot.get("end", ""))
        lines.append(f"{idx}. {start} - {end}".strip())
    return "\n".join(lines)


def _lead_context_text(state: GraphState) -> str:
    lines = [
        f"clinic_id: {state.get('clinic_id', '')}",
        f"thread_id: {state.get('thread_id', '')}",
        f"stage: {state.get('stage', 'qualify')}",
        f"intent: {state.get('intent', 'unknown')}",
    ]
    source_label = state.get("source_label")
    if source_label:
        lines.append(f"source_label: {source_label}")
    return "\n".join(lines)


def build_prompt_context(
    state: GraphState,
    *,
    current_message: str = "",
    slots: Optional[List[Dict[str, Any]]] = None,
    previous_summary: str = "",
) -> PromptContext:
    now = datetime.now(timezone.utc)
    time_context = f"utc_now: {now.isoformat()} | weekday_utc: {now.strftime('%A')}"

    return PromptContext(
        current_message=(current_message or "").strip(),
        history_window=_history_window_text(state),
        lead_context=_lead_context_text(state),
        time_context=time_context,
        slots_context=_slots_context_text(slots),
        previous_summary=previous_summary or str(state.get("chat_resumo", "")),
        last_agent_goal=str(state.get("last_agent_goal", "")),
        last_user_intent_raw=str(state.get("last_user_intent_raw", "")),
    )


def _profile_dir(profile: str) -> Path:
    return _BASE_DIR / profile


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_tag_block(content: str, tag: str) -> str:
    pattern = rf"<{tag}>\s*(.*?)\s*</{tag}>"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _load_shared_voice(profile: str) -> str:
    cache_key = f"shared:{profile}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    path = _profile_dir(profile) / "shared_voice.md"
    if not path.exists():
        _CACHE[cache_key] = _FALLBACK_SHARED_VOICE
        return _CACHE[cache_key]

    try:
        text = _read_file(path).strip()
    except Exception as exc:
        logger.warning("Prompt shared_voice read failed for profile=%s: %s", profile, exc)
        text = _FALLBACK_SHARED_VOICE

    _CACHE[cache_key] = text or _FALLBACK_SHARED_VOICE
    return _CACHE[cache_key]


def _load_prompt_template(profile: str, name: str) -> Tuple[str, str]:
    cache_key = f"prompt:{profile}:{name}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    path = _profile_dir(profile) / f"{name}.md"
    if not path.exists():
        logger.warning("Prompt file not found profile=%s name=%s. Using fallback.", profile, name)
        _CACHE[cache_key] = _FALLBACK_PROMPTS[name]
        return _CACHE[cache_key]

    try:
        content = _read_file(path)
        system_template = _extract_tag_block(content, "SYSTEM_PROMPT")
        user_template = _extract_tag_block(content, "USER_TEMPLATE")
        if not system_template or not user_template:
            raise ValueError("Missing SYSTEM_PROMPT or USER_TEMPLATE block")
    except Exception as exc:
        logger.warning("Prompt parse failed profile=%s name=%s: %s. Using fallback.", profile, name, exc)
        _CACHE[cache_key] = _FALLBACK_PROMPTS[name]
        return _CACHE[cache_key]

    _CACHE[cache_key] = (system_template, user_template)
    return _CACHE[cache_key]


def _render_template(template: str, context: PromptContext) -> str:
    normalized: Dict[str, str] = {}
    for key, value in context.items():
        normalized[key] = str(value if value is not None else "")
    return template.format_map(_SafeFormatDict(normalized)).strip()


def get_prompt_bundle(name: str, state: GraphState, context: PromptContext) -> PromptBundle:
    profile = get_prompt_profile(state)
    system_template, user_template = _load_prompt_template(profile, name)
    shared_voice = _load_shared_voice(profile)

    system_prompt = f"{shared_voice}\n\n{system_template}".strip() if shared_voice else system_template
    return PromptBundle(
        profile=profile,
        system_prompt=_render_template(system_prompt, context),
        user_prompt=_render_template(user_template, context),
    )

