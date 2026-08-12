from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

_PACIFIC = ZoneInfo("America/Los_Angeles")
_EASTERN = ZoneInfo("America/New_York")
_CENTRAL = ZoneInfo("America/Chicago")
_MOUNTAIN = ZoneInfo("America/Denver")

_TZ_MAP = {
    "PT": _PACIFIC, "PST": _PACIFIC, "PDT": _PACIFIC,
    "ET": _EASTERN, "EST": _EASTERN, "EDT": _EASTERN,
    "CT": _CENTRAL, "CST": _CENTRAL, "CDT": _CENTRAL,
    "MT": _MOUNTAIN, "MST": _MOUNTAIN, "MDT": _MOUNTAIN,
    "UTC": timezone.utc, "GMT": timezone.utc,
}

_TIME_RE = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)"
    r"(?:\s*(?P<tz>PT|PST|PDT|ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|UTC|GMT))?\b",
    re.I,
)
_RELATIVE_RE = re.compile(r"\b(today|tonight|tomorrow)\b", re.I)


def _message_reference(email: Dict[str, Any], tz) -> datetime:
    raw = email.get("ts") or email.get("timestamp") or email.get("internalDate")
    try:
        value = float(raw)
        if value > 10_000_000_000:  # Gmail internalDate can be milliseconds.
            value /= 1000.0
        if value > 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(tz)
    except Exception:
        pass
    return datetime.now(tz)


def extract_requested_time(email: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ground a simple explicit scheduling time from the message text.

    This is a deterministic safety layer, not an intent classifier. It exists so
    the assistant never stores an LLM-guessed meeting time when the email itself
    contains a concrete expression such as "5pm PST today".
    """
    text = "\n".join(
        str(email.get(k) or "") for k in ("subject", "body", "snippet")
    )
    match = _TIME_RE.search(text)
    if not match:
        return None

    tz_token = str(match.group("tz") or "").upper()
    tz = _TZ_MAP.get(tz_token) or _PACIFIC
    ref = _message_reference(email, tz)

    rel = _RELATIVE_RE.search(text)
    word = str(rel.group(1)).lower() if rel else "today"
    day = ref.date()
    if word == "tomorrow":
        day = day + timedelta(days=1)

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = str(match.group("ampm") or "").lower().replace(".", "")
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    local_dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    start_utc = local_dt.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(hours=1)
    return {
        "event_at_unix": int(start_utc.timestamp()),
        "time_min": start_utc.isoformat().replace("+00:00", "Z"),
        "time_max": end_utc.isoformat().replace("+00:00", "Z"),
        "timezone": getattr(tz, "key", str(tz)),
        "timezone_label": tz_token or "PT",
        "display": local_dt.strftime("%Y-%m-%d %I:%M %p") + f" {tz_token or 'PT'}",
        "source_text": match.group(0),
    }
