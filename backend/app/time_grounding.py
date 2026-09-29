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
_DATE_PATTERNS = [
    re.compile(r"\b(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(?P<year>20\d{2})\b", re.I),
    re.compile(r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>20\d{2})\b"),
]
_MONTHS = {name.lower(): i for i, names in enumerate([(), ('jan','january'),('feb','february'),('mar','march'),('apr','april'),('may',),('jun','june'),('jul','july'),('aug','august'),('sep','september'),('oct','october'),('nov','november'),('dec','december')]) for name in names}


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

    # Explicit calendar dates always win over the message timestamp. The old
    # implementation silently anchored "Sep 28, 4 PM" to the email date, which
    # caused valid meetings to disappear or land on the wrong day.
    day = None
    for pattern in _DATE_PATTERNS:
        dm = pattern.search(text)
        if not dm:
            continue
        month_raw = dm.group("month")
        month = int(month_raw) if str(month_raw).isdigit() else _MONTHS.get(str(month_raw).lower())
        if month:
            day = datetime(int(dm.group("year")), month, int(dm.group("day"))).date()
            break
    if day is None:
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


def extract_ics_time(data: bytes | str) -> Optional[Dict[str, Any]]:
    """Parse DTSTART/DTEND/TZID from an iCalendar attachment without an LLM."""
    try:
        text = data.decode("utf-8", errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data or "")
    except Exception:
        return None
    # Unfold RFC5545 continuation lines.
    text = re.sub(r"\r?\n[ \t]", "", text)
    m = re.search(r"^DTSTART(?P<params>[^:]*)[:](?P<value>[^\r\n]+)", text, re.I | re.M)
    if not m:
        return None
    params, value = m.group("params") or "", m.group("value").strip()
    tzid_m = re.search(r"TZID=([^;:]+)", params, re.I)
    tzid = tzid_m.group(1).strip() if tzid_m else ""
    try:
        if value.endswith("Z"):
            local = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            tz = timezone.utc
        else:
            fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
            naive = datetime.strptime(value[:15] if fmt.endswith('%S') else value[:13], fmt)
            try:
                tz = ZoneInfo(tzid) if tzid else timezone.utc
            except Exception:
                tz = timezone.utc
            local = naive.replace(tzinfo=tz)
        start_utc = local.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(hours=1)
        em = re.search(r"^DTEND(?P<params>[^:]*)[:](?P<value>[^\r\n]+)", text, re.I | re.M)
        if em:
            ev = em.group("value").strip()
            try:
                if ev.endswith("Z"):
                    end_utc = datetime.strptime(ev, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                else:
                    efmt = "%Y%m%dT%H%M%S" if len(ev) >= 15 else "%Y%m%dT%H%M"
                    enaive = datetime.strptime(ev[:15] if efmt.endswith('%S') else ev[:13], efmt)
                    end_utc = enaive.replace(tzinfo=tz).astimezone(timezone.utc)
            except Exception:
                pass
        return {
            "event_at_unix": int(start_utc.timestamp()),
            "event_end_unix": int(end_utc.timestamp()),
            "time_min": start_utc.isoformat().replace("+00:00", "Z"),
            "time_max": end_utc.isoformat().replace("+00:00", "Z"),
            "timezone": getattr(tz, "key", str(tz)),
            "timezone_label": tzid or "UTC",
            "display": local.strftime("%Y-%m-%d %I:%M %p") + (f" {tzid}" if tzid else " UTC"),
            "source_text": m.group(0),
        }
    except Exception:
        return None
