from __future__ import annotations
import os, re
from typing import Any, Dict

_MEETING_EVIDENCE_RE = re.compile(r"\b(meeting|appointment|calendar|interview|session|invite|invitation|scheduled|schedule)\b", re.I)

def is_meeting_candidate(email: Dict[str, Any], semantic: Dict[str, Any] | None = None) -> bool:
    sem = semantic or {}
    intent_text = " ".join(str(sem.get(k) or "") for k in ("intent", "email_type", "reason", "priority_reason")).upper()
    if any(token in intent_text for token in ("MEETING", "SCHEDUL", "APPOINTMENT", "CALENDAR", "INVITE", "INTERVIEW", "SESSION")):
        return True
    attachments = email.get("attachments") or []
    if any(str(a.get("filename") or "").lower().endswith(".ics") or "text/calendar" in str(a.get("mimeType") or a.get("mime_type") or "").lower() for a in attachments):
        return True
    return bool(_MEETING_EVIDENCE_RE.search(str(email.get("subject") or "")))

def focus_eligible(item: Dict[str, Any]) -> bool:
    bucket = str(item.get("bucket") or "").upper()
    label = str(item.get("label") or "").upper()
    important = {"IMPORTANT_NOW", "CONVERSATIONAL", "BUSINESS", "RECRUITING", "SECURITY", "FOLLOW_UP", "TRANSACTIONAL"}
    if bucket not in important or label == "LOW":
        return False
    score = float(item.get("inbox_score", 0) or 0)
    threshold = float(os.getenv("IMPORTANT_INBOX_MIN_SCORE", "0.38"))
    return bool(score >= threshold or item.get("requires_action") or item.get("respond_recommended") or item.get("security_event"))
