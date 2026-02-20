import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings

logger = logging.getLogger(__name__)


class SheetsService:
    def __init__(self):
        self.service = None
        self._setup_service()

    def _load_credentials(self):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        b64_creds = (settings.GCAL_CREDENTIALS_B64 or "").strip()

        if b64_creds:
            decoded = base64.b64decode(b64_creds).decode("utf-8")
            info = json.loads(decoded)
            return service_account.Credentials.from_service_account_info(info, scopes=scopes)

        if os.path.exists(settings.GCAL_CREDENTIALS_JSON):
            return service_account.Credentials.from_service_account_file(settings.GCAL_CREDENTIALS_JSON, scopes=scopes)

        return None

    def _setup_service(self) -> None:
        try:
            creds = self._load_credentials()
            if creds is None:
                logger.warning("Google Sheets credentials not found. Sheets sync disabled.")
                self.service = None
                return
            self.service = build("sheets", "v4", credentials=creds)
        except Exception as exc:
            logger.error("Failed to initialize Sheets service: %s", exc)
            self.service = None

    async def append_row(
        self,
        values: List[Any],
        spreadsheet_id: Optional[str] = None,
        range_name: Optional[str] = None,
    ) -> bool:
        sheet_id = spreadsheet_id or settings.GSHEETS_SPREADSHEET_ID
        target_range = range_name or settings.GSHEETS_RANGE
        if not sheet_id:
            logger.warning("GSHEETS_SPREADSHEET_ID not configured. Skipping sheets sync.")
            return False
        if self.service is None:
            logger.warning("Sheets service unavailable. Skipping sheets sync.")
            return False

        body = {"values": [values]}
        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            return True
        except Exception as exc:
            logger.error("Failed appending row to sheets: %s", exc)
            return False

    async def sync_followup(self, followup: Dict[str, Any]) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        values = [
            now_iso,
            followup.get("phone", ""),
            followup.get("lead_name", ""),
            followup.get("interesse", ""),
            followup.get("intent", ""),
            followup.get("stage", ""),
            followup.get("chat_resumo", ""),
            followup.get("thread_id", ""),
            followup.get("ai_response", ""),
        ]
        return await self.append_row(values)


sheets_service = SheetsService()

