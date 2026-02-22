import hashlib
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.api.routes.knowledge import router as knowledge_router
from app.config import settings
from app.db import db_service
from app.evolution import evolution_service
from app.gcal import gcal_service
from app.graph import app_graph
from app.services.audio_service import audio_service
from app.services.redis_service import redis_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DEDUP_TTL_SECONDS = 60 * 10
_seen_provider_events: Dict[str, float] = {}
_seen_provider_events_lock = Lock()
_BASE_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _BASE_DIR / "static"

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="SDR Agent Dental MVP",
)

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])


class ChatTestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[str] = None
    clinic_id: Optional[str] = None


class ChatTestResponse(BaseModel):
    thread_id: str
    response: str
    stage: str
    intent: str
    interesse: str
    prompt_profile: str


def _validate_webhook_secret(request: Request) -> bool:
    if not settings.EVOLUTION_WEBHOOK_SECRET:
        return True
    received = request.headers.get("x-webhook-secret", "")
    return received == settings.EVOLUTION_WEBHOOK_SECRET


def _mask_phone(phone: Optional[str]) -> str:
    if not phone:
        return "unknown"
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def _mask_text(text: Optional[str]) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    if len(compact) > 120:
        compact = compact[:120] + "..."
    compact = re.sub(r"\b\d{6,}\b", "[num]", compact)
    return compact


def _extract_provider_event_id(body: Dict[str, Any]) -> Optional[str]:
    if "data" in body:
        data = body.get("data", {})
        key = data.get("key", {})
        return key.get("id") or data.get("messageTimestamp")
    return body.get("event_id")


def _cleanup_seen_events(now: float) -> None:
    expired = [event_id for event_id, ts in _seen_provider_events.items() if now - ts > _DEDUP_TTL_SECONDS]
    for event_id in expired:
        _seen_provider_events.pop(event_id, None)


def _mark_duplicate_or_register(event_id: Optional[str]) -> bool:
    if not event_id:
        return False
    now = time.time()
    with _seen_provider_events_lock:
        _cleanup_seen_events(now)
        if event_id in _seen_provider_events:
            return True
        _seen_provider_events[event_id] = now
        return False


def _extract_payload(
    body: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str], bool, Optional[str], Optional[str], str, Optional[str]]:
    # Supports Evolution nested payload and a simple fallback payload for local tests.
    if "data" in body:
        data = body.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})
        if not isinstance(message, dict):
            message = {}

        from_me = bool(message.get("fromMe"))
        remote_jid = key.get("remoteJid") or data.get("remoteJid")
        phone = remote_jid.split("@")[0] if remote_jid else data.get("from")
        push_name = data.get("pushName") or body.get("name") or "Unknown"
        text_content = message.get("conversation") or message.get("extendedTextMessage", {}).get("text")

        audio_message = message.get("audioMessage", {})
        if not isinstance(audio_message, dict):
            audio_message = {}
        audio_url = audio_message.get("url") or data.get("audioUrl") or body.get("audio_url")
        audio_b64 = audio_message.get("base64") or data.get("audioBase64") or body.get("audio_base64")
        mime_type = audio_message.get("mimetype") or data.get("mimetype") or body.get("audio_mime_type") or "audio/ogg"
        message_id = key.get("id") or body.get("message_id")
        return phone, push_name, text_content, from_me, audio_url, audio_b64, mime_type, message_id

    phone = body.get("from")
    text_content = body.get("body")
    push_name = body.get("name", "Unknown")
    audio_url = body.get("audio_url")
    audio_b64 = body.get("audio_base64")
    mime_type = body.get("audio_mime_type", "audio/ogg")
    message_id = body.get("message_id")
    return phone, push_name, text_content, False, audio_url, audio_b64, mime_type, message_id


def _build_debounce_key(
    *,
    phone: Optional[str],
    provider_event_id: Optional[str],
    message_id: Optional[str],
    text_content: Optional[str],
    audio_url: Optional[str],
) -> str:
    base = provider_event_id or message_id or text_content or audio_url or str(time.time())
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    prefix = phone or "unknown"
    return f"{prefix}:{digest}"


def _format_slot_for_user(slot_start: Optional[str]) -> str:
    raw = (slot_start or "").strip()
    if not raw:
        return "horario combinado"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m as %H:%M")
    except ValueError:
        return raw


def _extract_response_text(result: Dict[str, Any]) -> str:
    messages = result.get("messages", [])
    if messages:
        last_message = messages[-1]
        content = getattr(last_message, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    chunks.append(str(item["text"]))
            if chunks:
                return " ".join(chunks).strip()
        if content:
            return str(content).strip()

    output_text = result.get("output_text", "")
    return str(output_text).strip()


async def _run_post_attendance_actions(
    *,
    remote_jid: str,
    ai_response: str,
    conversation_id: str,
    message_id: Optional[str],
    followup_payload: Dict[str, Any],
) -> None:
    try:
        await db_service.create_message(conversation_id, ai_response, "ai")
    except Exception as exc:
        logger.error("Failed to save AI outbound message: %s", exc)

    try:
        await evolution_service.mark_as_read(remote_jid, message_id=message_id)
        await evolution_service.send_presence(remote_jid, presence="composing")
    except Exception as exc:
        logger.error("Failed to trigger Evolution read/presence actions: %s", exc)

    import asyncio
    # Calcula delay natural baseado no tamanho da resposta (max 8s, min 1.5s)
    delay_seconds = max(1.5, min(8.0, len(ai_response) / 25.0))
    await asyncio.sleep(delay_seconds)

    try:
        await evolution_service.send_message(remote_jid, ai_response)
    except Exception as exc:
        logger.error("Failed to send outbound message to Evolution: %s", exc)

    try:
        await db_service.save_followup(**followup_payload)
    except Exception as exc:
        logger.error("Failed to persist follow-up metrics: %s", exc)


async def _resolve_text_from_audio(
    text_content: Optional[str],
    audio_url: Optional[str],
    audio_b64: Optional[str],
    mime_type: str,
) -> str:
    normalized_text = (text_content or "").strip()
    if normalized_text:
        return normalized_text
    if not audio_url and not audio_b64:
        return ""
    transcription = await audio_service.transcribe(
        audio_url=audio_url,
        audio_base64=audio_b64,
        mime_type=mime_type,
    )
    return transcription.strip()


async def _process_evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    if not _validate_webhook_secret(request):
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    body = await request.json()
    provider_event_id = _extract_provider_event_id(body)
    if _mark_duplicate_or_register(provider_event_id):
        logger.info("Ignoring duplicate provider event id=%s", provider_event_id)
        return {"status": "ignored_duplicate"}

    phone, push_name, text_content, from_me, audio_url, audio_b64, mime_type, message_id = _extract_payload(body)
    text_content = await _resolve_text_from_audio(text_content, audio_url, audio_b64, mime_type)

    logger.info(
        "Received webhook event_id=%s phone=%s text=%s from_me=%s",
        provider_event_id,
        _mask_phone(phone),
        _mask_text(text_content),
        from_me,
    )

    if from_me:
        return {"status": "ignored_self"}
    if not phone or not text_content:
        return {"status": "ignored_no_content"}

    debounce_key = _build_debounce_key(
        phone=phone,
        provider_event_id=provider_event_id,
        message_id=message_id,
        text_content=text_content,
        audio_url=audio_url,
    )
    debounce_allowed = await redis_service.acquire_debounce_lock(debounce_key)
    if not debounce_allowed:
        logger.info("Ignoring debounced message for key=%s", debounce_key)
        return {"status": "ignored_debounce"}

    remote_jid = f"{phone}@s.whatsapp.net"
    clinic_id = settings.CLINIC_ID_PILOT

    lead = await db_service.get_or_create_lead(phone, push_name, clinic_id)
    conversation = await db_service.get_or_create_conversation(lead["id"], clinic_id)
    logger.info("thread_id=%s processing inbound message", conversation["id"])
    await db_service.create_message(conversation["id"], text_content, "user")

    inputs = {
        "messages": [HumanMessage(content=text_content)],
        "clinic_id": clinic_id,
        "thread_id": conversation["id"],
    }
    config = {"configurable": {"thread_id": conversation["id"]}}
    result = await app_graph.ainvoke(inputs, config=config)

    ai_response = _extract_response_text(result)
    if not ai_response:
        logger.warning("thread_id=%s graph returned no response text", conversation["id"])
        return {"status": "no_response"}

    selected_slot = result.get("selected_slot") or {}
    if result.get("stage") == "done" and selected_slot:
        appointment = await db_service.create_appointment(
            lead_id=lead["id"],
            clinic_id=clinic_id,
            slot_time=selected_slot["start"],
            procedure_name="consulta",
            status="requested",
        )
        gcal_event = gcal_service.create_event(
            summary=f"Consulta - {push_name or phone}",
            start_time=selected_slot["start"],
            end_time=selected_slot["end"],
            description=f"Telefone: {phone}\nAgendado via SDR IA",
        )
        await db_service.mark_appointment_confirmed(appointment["id"], gcal_event.get("id"))
        logger.info(
            "thread_id=%s appointment_confirmed appointment_id=%s google_event_id=%s",
            conversation["id"],
            appointment["id"],
            gcal_event.get("id"),
        )
        slot_label = _format_slot_for_user(selected_slot.get("start"))
        ai_response = (
            f"Perfeito! Seu agendamento foi confirmado para {slot_label}."
            " Se precisar remarcar, me avise por aqui."
        )

    followup_payload = {
        "thread_id": conversation["id"],
        "conversation_id": conversation["id"],
        "lead_id": lead["id"],
        "clinic_id": clinic_id,
        "phone": phone,
        "lead_name": push_name or "",
        "interesse": str(result.get("interesse") or "baixo_interesse"),
        "intent": str(result.get("intent") or "unknown"),
        "stage": str(result.get("stage") or "qualify"),
        "chat_resumo": str(result.get("chat_resumo") or ""),
        "ai_response": ai_response,
        "selected_slot_start": selected_slot.get("start"),
        "selected_slot_end": selected_slot.get("end"),
    }

    background_tasks.add_task(
        _run_post_attendance_actions,
        remote_jid=remote_jid,
        ai_response=ai_response,
        conversation_id=conversation["id"],
        message_id=message_id,
        followup_payload=followup_payload,
    )
    logger.info("thread_id=%s post-attendance tasks scheduled", conversation["id"])

    return {"status": "processed", "thread_id": conversation["id"], "interesse": followup_payload["interesse"]}


@app.get("/")
def read_root():
    return {"message": "SDR Agent Dental API is running", "version": settings.VERSION}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/chat")
def chat_page():
    chat_path = _STATIC_DIR / "chat.html"
    if not chat_path.exists():
        raise HTTPException(status_code=404, detail="chat interface not found")
    return FileResponse(chat_path)


@app.post("/api/chat/test", response_model=ChatTestResponse)
async def chat_test(payload: ChatTestRequest):
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="message cannot be empty")

    thread_id = (payload.thread_id or "").strip() or str(uuid4())
    clinic_id = (payload.clinic_id or "").strip() or settings.CLINIC_ID_PILOT or "demo-clinic"

    inputs = {
        "messages": [HumanMessage(content=message_text)],
        "clinic_id": clinic_id,
        "thread_id": thread_id,
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await app_graph.ainvoke(inputs, config=config)
    except Exception as exc:
        logger.error("Error processing /api/chat/test: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="chat test failed")

    response_text = _extract_response_text(result) or "Nao consegui responder agora, tente novamente."
    return ChatTestResponse(
        thread_id=thread_id,
        response=response_text,
        stage=str(result.get("stage") or "qualify"),
        intent=str(result.get("intent") or "unknown"),
        interesse=str(result.get("interesse") or "baixo_interesse"),
        prompt_profile=str(result.get("prompt_profile") or settings.PROMPT_PROFILE),
    )


@app.post("/api/webhook")
async def webhook_entrypoint(request: Request, background_tasks: BackgroundTasks):
    try:
        return await _process_evolution_webhook(request, background_tasks)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error processing webhook /api/webhook: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc)}


@app.post("/webhook/evolution")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        return await _process_evolution_webhook(request, background_tasks)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error processing webhook /webhook/evolution: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc)}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
