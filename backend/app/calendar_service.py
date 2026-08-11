from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.integration_store import get_connection

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _credentials(user_id: str) -> Credentials:
    stored = get_connection(user_id, "google")
    if not stored:
        raise RuntimeError("Google account is not connected")
    data = stored["credentials"]
    creds = Credentials(
        token=data.get("token"), refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"), client_id=data.get("client_id"),
        client_secret=data.get("client_secret"), scopes=data.get("scopes") or [],
    )
    if CALENDAR_SCOPE not in set(creds.scopes or []):
        raise RuntimeError("Calendar permission is not granted. Reconnect Google once to enable availability checks.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def free_busy(user_id: str, time_min: str, time_max: str) -> Dict[str, Any]:
    """Read-only availability lookup. Never creates or changes calendar events."""
    creds = _credentials(user_id)
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    result = svc.freebusy().query(body={"timeMin": time_min, "timeMax": time_max, "items": [{"id": "primary"}]}).execute()
    busy = ((result.get("calendars") or {}).get("primary") or {}).get("busy") or []
    return {"time_min": time_min, "time_max": time_max, "busy": busy, "source": "google_calendar_readonly"}
