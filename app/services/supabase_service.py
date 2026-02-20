import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self, url: Optional[str] = None, service_role_key: Optional[str] = None):
        self._url = url
        self._service_role_key = service_role_key
        self._client: Optional[Client] = None

    @property
    def url(self) -> str:
        return self._url if self._url is not None else settings.SUPABASE_URL

    @property
    def service_role_key(self) -> str:
        return self._service_role_key if self._service_role_key is not None else settings.SUPABASE_SERVICE_ROLE_KEY

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self.url or not self.service_role_key:
                raise ValueError("Supabase credentials not configured")
            self._client = create_client(self.url, self.service_role_key)
        return self._client

    async def check_connection(self) -> bool:
        try:
            # Lightweight query to validate project and credentials.
            self.client.table("clinics").select("id").limit(1).execute()
            return True
        except Exception as exc:
            logger.error("Supabase connection check failed: %s", exc)
            return False

    async def get_or_create_lead(self, phone: str, name: Optional[str] = None, clinic_id: Optional[str] = None):
        """Busca um lead pelo telefone ou cria se nao existir."""
        try:
            response = self.client.table("leads").select("*").eq("phone", phone).eq("clinic_id", clinic_id).execute()
            if response.data:
                return response.data[0]

            lead_data = {"phone": phone, "name": name, "clinic_id": clinic_id}
            response = self.client.table("leads").insert(lead_data).execute()
            return response.data[0]
        except Exception as exc:
            logger.error("Error in get_or_create_lead: %s", exc)
            raise

    async def get_or_create_conversation(self, lead_id: str, clinic_id: str):
        """Busca conversa ativa ou cria nova."""
        try:
            response = (
                self.client.table("conversations")
                .select("*")
                .eq("lead_id", lead_id)
                .eq("clinic_id", clinic_id)
                .eq("status", "active")
                .execute()
            )
            if response.data:
                return response.data[0]

            conv_data = {"lead_id": lead_id, "clinic_id": clinic_id, "status": "active"}
            response = self.client.table("conversations").insert(conv_data).execute()
            return response.data[0]
        except Exception as exc:
            logger.error("Error in get_or_create_conversation: %s", exc)
            raise

    async def create_message(self, conversation_id: str, content: str, sender_type: str) -> None:
        """Registra uma mensagem no banco."""
        try:
            msg_data = {"conversation_id": conversation_id, "content": content, "sender_type": sender_type}
            self.client.table("messages").insert(msg_data).execute()
        except Exception as exc:
            logger.error("Error creating message: %s", exc)
            raise

    async def create_appointment(
        self,
        lead_id: str,
        clinic_id: str,
        slot_time: str,
        procedure_name: Optional[str] = None,
        status: str = "requested",
    ) -> Dict[str, Any]:
        """Cria um registro de agendamento."""
        try:
            appt_data = {
                "lead_id": lead_id,
                "clinic_id": clinic_id,
                "slot_time": slot_time,
                "procedure_name": procedure_name,
                "status": status,
            }
            response = self.client.table("appointments").insert(appt_data).execute()
            return response.data[0]
        except Exception as exc:
            logger.error("Error creating appointment: %s", exc)
            raise

    async def mark_appointment_confirmed(self, appointment_id: str, google_event_id: Optional[str] = None):
        """Atualiza status do agendamento para confirmado."""
        try:
            patch: Dict[str, Any] = {"status": "confirmed"}
            if google_event_id:
                patch["google_event_id"] = google_event_id

            response = self.client.table("appointments").update(patch).eq("id", appointment_id).execute()
            return response.data[0] if response.data else None
        except Exception as exc:
            logger.error("Error confirming appointment: %s", exc)
            raise

    async def save_followup(
        self,
        *,
        thread_id: str,
        conversation_id: str,
        lead_id: str,
        clinic_id: str,
        phone: str,
        lead_name: str,
        interesse: str,
        intent: str,
        stage: str,
        chat_resumo: str,
        ai_response: str,
        selected_slot_start: Optional[str] = None,
        selected_slot_end: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persiste métricas de pós-atendimento em `tb_followup`."""
        payload: Dict[str, Any] = {
            "thread_id": thread_id,
            "conversation_id": conversation_id,
            "lead_id": lead_id,
            "clinic_id": clinic_id,
            "phone": phone,
            "lead_name": lead_name,
            "interesse": interesse,
            "intent": intent,
            "stage": stage,
            "chat_resumo": chat_resumo,
            "ai_response": ai_response,
            "selected_slot_start": selected_slot_start,
            "selected_slot_end": selected_slot_end,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        tables = ("tb_followup", "followups")
        last_error: Optional[Exception] = None
        for table_name in tables:
            try:
                response = self.client.table(table_name).insert(payload).execute()
                if response.data:
                    return response.data[0]
                return payload
            except Exception as exc:
                last_error = exc
                logger.warning("Could not insert follow-up in table `%s`: %s", table_name, exc)

        if last_error:
            logger.error("Follow-up persistence failed in all candidate tables: %s", last_error)
        return None


db_service = SupabaseService()
