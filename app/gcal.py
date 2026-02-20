import logging
import os
import base64
import json
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from app.config import settings

logger = logging.getLogger(__name__)


class GCalService:
    def __init__(self):
        self.creds = None
        self.service = None
        self._setup_service()

    def _setup_service(self):
        try:
            scopes = ["https://www.googleapis.com/auth/calendar"]
            b64_creds = (settings.GCAL_CREDENTIALS_B64 or "").strip()

            if b64_creds:
                # Preferred in deploy: avoids mounting a credentials file.
                creds_json = base64.b64decode(b64_creds).decode("utf-8")
                creds_info = json.loads(creds_json)
                self.creds = service_account.Credentials.from_service_account_info(
                    creds_info,
                    scopes=scopes,
                )
            elif os.path.exists(settings.GCAL_CREDENTIALS_JSON):
                self.creds = service_account.Credentials.from_service_account_file(
                    settings.GCAL_CREDENTIALS_JSON,
                    scopes=scopes,
                )
            else:
                logger.warning(
                    "GCal credentials not found (file=%s, b64=empty). Using Mock mode.",
                    settings.GCAL_CREDENTIALS_JSON,
                )
                return

            self.service = build("calendar", "v3", credentials=self.creds)
            logger.info("GCal Service initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize GCal service: {e}. Using Mock mode.")

    def create_event(
        self, summary: str, start_time: str, end_time: str, description: str = ""
    ) -> Dict[str, Any]:
        """Cria um evento no Google Calendar (Real se credenciais existirem, senao Mock)."""
        if not self.service:
            logger.info(f"[MOCK] Creating GCal Event: {summary} at {start_time}")
            return {
                "id": "mock_event_id",
                "link": "http://google.com/calendar/event?eid=mock",
                "status": "mock_confirmed",
            }

        try:
            event = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start_time,
                    "timeZone": "America/Sao_Paulo",
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": "America/Sao_Paulo",
                },
            }

            event_result = (
                self.service.events().insert(
                    calendarId=settings.GCAL_CALENDAR_ID,
                    body=event,
                ).execute()
            )
            logger.info(f"Event created: {event_result.get('htmlLink')}")
            return event_result
        except Exception as e:
            logger.error(f"Error creating event in GCal: {e}")
            raise e


gcal_service = GCalService()
