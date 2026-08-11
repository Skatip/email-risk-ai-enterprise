from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from app.ai.provider import AIProviderError, get_ai_provider


TRIAGE_SYSTEM_PROMPT = """You are the semantic inbox triage layer for an AI communication assistant.
Rank messages like a careful human executive assistant. Understand meaning and sender expectation; never classify from isolated keywords.

Prioritize when relevant:
1. direct human conversations/replies,
2. requests requiring the user's action, decision, response, payment, review, approval, scheduling, or attention,
3. genuine security/account/fraud incidents,
4. important personal/family communication,
5. important work, education, client, recruiter, application-status, travel, healthcare, legal, or financial communication,
6. documents, deadlines, commitments, and time-sensitive changes,
7. useful informational messages.

De-prioritize when no meaningful action/consequence exists:
- job recommendation feeds and job-alert digests,
- newsletters and bulk university/company broadcasts,
- marketing/promotions,
- social updates,
- automated informational notifications,
- low-value spam.

Critical distinctions:
- A company/job title containing the word 'security' is NOT a security event. security_event=true only for actual account access, authentication, password/MFA changes, suspicious activity, fraud, compromise, or comparable security incidents.
- gmail.com/outlook.com/yahoo.com does NOT prove family/personal. Infer relationship from the message and conversation evidence.
- 'job', 'university', 'course', 'recruiting', etc. do NOT automatically make a message important. Distinguish direct communication/application outcome from a bulk feed.
- An automated message can still be important: rejection/offer/application update, overdue bill, fraud alert, flight cancellation, deadline, medical result, school action, etc.
- A Spam message can still be genuine human/work communication.
- Importance is not the same as urgency. A personally consequential result can be medium importance even if no action is required.
- Never invent facts.

Assign exactly one product bucket:
IMPORTANT_NOW, CONVERSATIONAL, BUSINESS, RECRUITING, SECURITY, FOLLOW_UP, TRANSACTIONAL, INFORMATIONAL, JOB_FEED, MARKETING, SOCIAL, AUTOMATED_LOW_VALUE, SPAM.
IMPORTANT_NOW is reserved for messages with meaningful consequence/action/deadline/security or high-value direct communication.
Use communication_type CONVERSATIONAL, AUTOMATED, or MIXED.
Return only the required JSON fields. Keep reason and priority_reason under 180 characters each."""


DEEP_ANALYSIS_PROMPT = """You are the email-understanding layer of a high-quality communication assistant.
Read the complete email body, recent thread context, and document intelligence like a careful human. Determine what actually happened, what the sender expects, whether action/reply is needed, relationship, consequence, urgency, and genuine risk.

Rules:
- Do not rely on keyword matching.
- A company/name containing 'security' is not a security incident unless the event itself concerns account/fraud/security.
- A consumer email domain does not establish a family/personal relationship.
- Distinguish automated application/recruiting status updates from job feeds and from direct recruiter conversations.
- Distinguish university newsletters from professor/advisor/administrative requests that require action.
- Importance combines personal relevance, consequence, action, deadline, and relationship. It is not only urgency.
- If no reply is needed, choose NO_REPLY and explain why. Do not turn NO_REPLY into ASK_USER just to be helpful.
- ASK_USER only when a reply/action is appropriate but essential user-owned information is missing.
- Never invent dates, amounts, availability, decisions, commitments, identities, or document facts.
- Detect concrete future obligations/reminders (meetings, deadlines, promised reviews, payments, callbacks). If a reminder is useful, return follow_up with needed=true and a grounded remind_at_unix. Resolve relative words such as "today" using current_unix and the message timestamp; if the time cannot be grounded, use null rather than guessing.
- commitments must contain only explicit or strongly supported user obligations from the message/thread.

Use a semantic intent such as DIRECT_REQUEST, HUMAN_CONVERSATION, RECRUITING_UPDATE, APPLICATION_STATUS, MEETING_REQUEST, PAYMENT_OR_BILL, SECURITY_ALERT, TRAVEL_UPDATE, EDUCATION_ACTION, DOCUMENT_REVIEW, AUTOMATED_INFORMATION, NEWSLETTER, JOB_FEED, PROMOTION, SOCIAL_UPDATE, SPAM.
Return only the required JSON fields."""


TRIAGE_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "inbox_score": {"type": "number", "minimum": 0, "maximum": 1},
        "priority": {"type": "number", "minimum": 0, "maximum": 1},
        "label": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "bucket": {"type": "string", "enum": ["IMPORTANT_NOW", "CONVERSATIONAL", "BUSINESS", "RECRUITING", "SECURITY", "FOLLOW_UP", "TRANSACTIONAL", "INFORMATIONAL", "JOB_FEED", "MARKETING", "SOCIAL", "AUTOMATED_LOW_VALUE", "SPAM"]},
        "communication_type": {"type": "string", "enum": ["CONVERSATIONAL", "AUTOMATED", "MIXED"]},
        "email_type": {"type": "string", "maxLength": 64},
        "relationship_type": {"type": "string", "maxLength": 64},
        "sender_type": {"type": "string", "enum": ["PERSONAL", "COMPANY", "AUTOMATED", "UNKNOWN"]},
        "intent": {"type": "string", "maxLength": 64},
        "direct_human": {"type": "boolean"},
        "requires_action": {"type": "boolean"},
        "security_event": {"type": "boolean"},
        "security_reason": {"type": "string", "maxLength": 180},
        "respond_recommended": {"type": "boolean"},
        "reply_decision": {"type": "string", "enum": ["DRAFT_REPLY", "NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"]},
        "risk": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 220},
        "priority_reason": {"type": "string", "maxLength": 180},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "id", "inbox_score", "priority", "label", "bucket", "communication_type", "email_type", "relationship_type", "sender_type",
        "intent", "direct_human", "requires_action", "security_event", "security_reason",
        "respond_recommended", "reply_decision", "risk", "reason", "priority_reason", "confidence",
    ],
}

TRIAGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {"type": "array", "items": TRIAGE_ITEM_SCHEMA},
    },
    "required": ["items"],
}

DEEP_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "priority": {"type": "number", "minimum": 0, "maximum": 1},
        "label": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "risk": {"type": "number", "minimum": 0, "maximum": 1},
        "intent": {"type": "string"},
        "sender_type": {"type": "string", "enum": ["PERSONAL", "COMPANY", "AUTOMATED", "UNKNOWN"]},
        "email_type": {"type": "string", "maxLength": 64},
        "relationship_type": {"type": "string", "maxLength": 64},
        "direct_human": {"type": "boolean"},
        "requires_action": {"type": "boolean"},
        "security_event": {"type": "boolean"},
        "security_reason": {"type": "string"},
        "respond_recommended": {"type": "boolean"},
        "reply_decision": {"type": "string", "enum": ["DRAFT_REPLY", "NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"]},
        "reason": {"type": "string"},
        "priority_reason": {"type": "string"},
        "urgency": {"type": "string"},
        "known_facts": {"type": "array", "items": {"type": "string"}},
        "unknown_facts": {"type": "array", "items": {"type": "string"}},
        "follow_up": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "needed": {"type": "boolean"},
                "remind_at_unix": {"type": ["number", "null"]},
                "note": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["needed", "remind_at_unix", "note", "reason"],
        },
        "commitments": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "priority", "label", "risk", "intent", "sender_type", "email_type", "relationship_type",
        "direct_human", "requires_action", "security_event", "security_reason", "respond_recommended",
        "reply_decision", "reason", "priority_reason", "urgency", "known_facts", "unknown_facts", "follow_up", "commitments", "confidence",
    ],
}


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _normalize_item(raw: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    priority = _safe_float(raw.get("priority"), 0.0)
    label = str(raw.get("label") or "").upper()
    if label not in {"HIGH", "MEDIUM", "LOW"}:
        label = "HIGH" if priority >= 0.72 else "MEDIUM" if priority >= 0.40 else "LOW"

    decision = str(raw.get("reply_decision") or "NO_REPLY").upper()
    if decision not in {"DRAFT_REPLY", "NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"}:
        decision = "NO_REPLY"

    security_event = bool(raw.get("security_event"))
    respond = bool(raw.get("respond_recommended")) and decision in {"DRAFT_REPLY"}

    return {
        "id": str(raw.get("id") or fallback.get("id") or ""),
        "inbox_score": _safe_float(raw.get("inbox_score"), priority),
        "priority": priority,
        "label": label,
        "bucket": str(raw.get("bucket") or "INFORMATIONAL").upper(),
        "communication_type": str(raw.get("communication_type") or ("CONVERSATIONAL" if raw.get("direct_human") else "AUTOMATED")).upper(),
        "email_type": str(raw.get("email_type") or "UNCLASSIFIED").upper(),
        "relationship_type": str(raw.get("relationship_type") or "UNKNOWN").upper(),
        "sender_type": str(raw.get("sender_type") or "UNKNOWN").upper(),
        "intent": str(raw.get("intent") or "UNCLASSIFIED").upper(),
        "direct_human": bool(raw.get("direct_human")),
        "requires_action": bool(raw.get("requires_action")),
        "security_event": security_event,
        "security_reason": str(raw.get("security_reason") or "").strip() if security_event else "",
        "respond_recommended": respond,
        "reply_decision": decision,
        "risk": _safe_float(raw.get("risk")),
        "reason": _clip(raw.get("reason") or "Semantic triage completed.", 220),
        "priority_reason": _clip(raw.get("priority_reason") or raw.get("reason") or "", 220),
        "confidence": _safe_float(raw.get("confidence"), 0.5),
    }


def _unavailable_item(original: Dict[str, Any]) -> Dict[str, Any]:
    """Conservative non-semantic fallback. Never pretends keyword rules are intelligence."""
    return {
        "id": str(original.get("id") or ""),
        "inbox_score": 0.12,
        "priority": 0.12,
        "label": "LOW",
        "bucket": "INFORMATIONAL",
        "communication_type": "AUTOMATED",
        "email_type": "UNCLASSIFIED",
        "relationship_type": "UNKNOWN",
        "sender_type": "UNKNOWN",
        "intent": "UNCLASSIFIED",
        "direct_human": False,
        "requires_action": False,
        "security_event": False,
        "security_reason": "",
        "respond_recommended": False,
        "reply_decision": "NO_REPLY",
        "risk": 0.0,
        "reason": "Semantic triage was temporarily unavailable; open the email for full analysis.",
        "priority_reason": "Not ranked by fallback keywords.",
        "confidence": 0.0,
    }


def _compact_payload(message: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(message.get("id") or ""),
        "thread_id": message.get("threadId"),
        "from": _clip(message.get("from"), 180),
        "subject": _clip(message.get("subject"), 220),
        "snippet": _clip(message.get("snippet"), 420),
        "timestamp": message.get("ts"),
        "source_folder": message.get("source_folder"),
        "labels": (message.get("labelIds") or [])[:8],
        "has_attachments": bool(message.get("attachments")),
        "attachment_names": [_clip(a.get("filename"), 100) for a in (message.get("attachments") or [])[:3]],
    }


def _triage_batch(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    provider = get_ai_provider()
    payload = [_compact_payload(m) for m in batch]
    max_tokens = int(os.getenv("INBOX_TRIAGE_BATCH_MAX_TOKENS", "2000"))
    try:
        response = provider.generate_json(
            system=TRIAGE_SYSTEM_PROMPT,
            user={"messages": payload},
            max_tokens=max_tokens,
            temperature=0.0,
            schema=TRIAGE_SCHEMA,
            schema_name="email_triage_batch",
        )
    except AIProviderError:
        # One bounded retry with half the batch prevents one long completion from
        # destroying the whole inbox. The caller handles splitting recursively.
        raise

    by_id: Dict[str, Dict[str, Any]] = {}
    for item in response.get("items") or []:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item
    return [_normalize_item(by_id.get(str(m.get("id")), {}), m) if str(m.get("id")) in by_id else _unavailable_item(m) for m in batch]


def _triage_batch_resilient(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        return _triage_batch(batch)
    except Exception as exc:
        if len(batch) <= 2:
            print(f"Semantic triage batch failed for {len(batch)} message(s): {exc}")
            return [_unavailable_item(m) for m in batch]
        mid = len(batch) // 2
        # Bounded divide-and-retry: at most a few smaller calls, never an unbounded loop.
        return _triage_batch_resilient(batch[:mid]) + _triage_batch_resilient(batch[mid:])


def triage_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Semantically rank a candidate pool in compact bounded batches."""
    if not messages:
        return []

    max_candidates = int(os.getenv("INBOX_TRIAGE_MAX_CANDIDATES", "60"))
    batch_size = max(4, min(12, int(os.getenv("INBOX_TRIAGE_BATCH_SIZE", "8"))))
    selected = messages[:max_candidates]
    batches = [selected[start:start + batch_size] for start in range(0, len(selected), batch_size)]
    # Triage batches are independent. Run a few concurrently so inbox latency is the
    # slowest compact model call, not the sum of every batch. Keep concurrency bounded.
    workers = max(1, min(int(os.getenv("INBOX_TRIAGE_CONCURRENCY", "3")), len(batches)))
    by_id: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_triage_batch_resilient, batch) for batch in batches]
        for future in as_completed(futures):
            for item in future.result():
                by_id[str(item.get("id") or "")] = item
    return [by_id.get(str(m.get("id") or ""), _unavailable_item(m)) for m in selected]


def analyze_message_semantics(
    email: Dict[str, Any],
    existing: Dict[str, Any] | None = None,
    *,
    thread: List[Dict[str, Any]] | None = None,
    attachment_context: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    provider = get_ai_provider()
    recent_thread = []
    for message in (thread or [])[-5:]:
        recent_thread.append(
            {
                "from": _clip(message.get("from"), 180),
                "to": _clip(message.get("to"), 180),
                "subject": _clip(message.get("subject"), 240),
                "body": _clip(message.get("body") or message.get("snippet"), 2200),
                "timestamp": message.get("ts"),
            }
        )

    docs = []
    for item in (attachment_context or [])[:6]:
        docs.append(
            {
                "filename": item.get("filename"),
                "document_type": item.get("document_type"),
                "title": item.get("title"),
                "summary": _clip(item.get("summary"), 700),
                "key_details": (item.get("key_details") or [])[:8],
                "action_items": (item.get("action_items") or [])[:6],
                "dates": (item.get("dates") or [])[:6],
                "amounts": (item.get("amounts") or [])[:6],
                "reply_context": _clip(item.get("reply_context"), 500),
            }
        )

    response = provider.generate_json(
        system=DEEP_ANALYSIS_PROMPT,
        user={
            "message": {
                "id": email.get("id"),
                "thread_id": email.get("threadId"),
                "from": _clip(email.get("from"), 260),
                "to": _clip(email.get("to"), 260),
                "subject": _clip(email.get("subject"), 420),
                "body": _clip(email.get("body") or email.get("snippet"), 10000),
                "timestamp": email.get("ts"),
                "source_folder": email.get("source_folder"),
            },
            "recent_thread": recent_thread,
            "attachment_intelligence": docs,
            "prior_triage": existing or {},
            "current_unix": int(time.time()),
        },
        max_tokens=int(os.getenv("EMAIL_ANALYSIS_MAX_TOKENS", "1100")),
        temperature=0.0,
        schema=DEEP_SCHEMA,
        schema_name="email_deep_analysis",
    )
    normalized = _normalize_item(response if isinstance(response, dict) else {}, email)
    normalized.update(
        {
            "urgency": str((response or {}).get("urgency") or "normal"),
            "known_facts": (response or {}).get("known_facts") or [],
            "unknown_facts": (response or {}).get("unknown_facts") or [],
            "follow_up": (response or {}).get("follow_up") or {"needed": False, "remind_at_unix": None, "note": "", "reason": ""},
            "commitments": (response or {}).get("commitments") or [],
        }
    )
    return normalized
