from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.integration_store import get_connection, update_connection_credentials

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _credentials(user_id: str) -> Credentials:
    stored = get_connection(user_id, "google")
    if not stored:
        raise RuntimeError("Google account is not connected")
    data = stored["credentials"]
    expiry = None
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(str(data["expiry"]).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            expiry = None
    creds = Credentials(
        token=data.get("token"), refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"), client_id=data.get("client_id"),
        client_secret=data.get("client_secret"), scopes=data.get("scopes") or [], expiry=expiry,
    )
    if CALENDAR_SCOPE not in set(creds.scopes or []):
        raise RuntimeError("Calendar permission is not granted. Reconnect Google once to enable availability checks.")
    if (not creds.valid or creds.expired) and creds.refresh_token:
        creds.refresh(Request())
        refreshed = dict(data)
        refreshed.update({"token": creds.token, "refresh_token": creds.refresh_token or data.get("refresh_token"), "expiry": creds.expiry.isoformat() if creds.expiry else None})
        update_connection_credentials(user_id, "google", refreshed, stored.get("account_email"))
    if not creds.valid:
        raise RuntimeError("Google authorization expired. Please reconnect Google.")
    return creds


def free_busy(user_id: str, time_min: str, time_max: str) -> Dict[str, Any]:
    """Read-only availability lookup. Never creates or changes calendar events."""
    creds = _credentials(user_id)
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    result = svc.freebusy().query(body={"timeMin": time_min, "timeMax": time_max, "items": [{"id": "primary"}]}).execute()
    busy = ((result.get("calendars") or {}).get("primary") or {}).get("busy") or []
    return {"time_min": time_min, "time_max": time_max, "busy": busy, "source": "google_calendar_readonly"}
