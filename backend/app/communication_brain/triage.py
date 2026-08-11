from __future__ import annotations

import os
from typing import Any, Dict, List

from app.ai.provider import get_ai_provider


TRIAGE_SYSTEM_PROMPT = """You are the semantic inbox triage layer for an AI communication assistant.
Rank messages the way a careful human assistant would, using meaning and context rather than keyword rules.

Your job is to decide which messages deserve space in an intelligent inbox.
Prioritize, in this order when appropriate:
1. direct human conversations and replies,
2. messages requiring the user's action, decision, response, payment, review, or attention,
3. genuine security/account incidents,
4. important personal/family communication,
5. important work/school/client/recruiter communication,
6. important documents, deadlines, or commitments,
7. useful informational messages.

De-prioritize:
- job-alert feeds and recommendation digests,
- newsletters,
- marketing/promotions,
- bulk notifications,
- social updates,
- automated informational mail with no required action,
- low-value spam.

Critical rules:
- Do NOT infer security merely because a company, job title, or subject contains the word 'security'. A security_event is true only when the message concerns account access, authentication, password/MFA changes, suspicious activity, fraud, compromise, or a comparable actual security incident.
- Do NOT infer family/personal merely from gmail.com/outlook.com/yahoo.com. Infer relationship from the communication itself.
- Do NOT treat 'job', 'university', 'course', or similar words as automatically important. Distinguish a direct person asking something from a bulk feed/newsletter.
- A message can be automated and still important (for example a real fraud alert, overdue payment, flight cancellation, or deadline).
- A message can be in Spam and still be a genuine human/work conversation.
- Do not invent facts.

Return JSON only with an `items` array. Return exactly one result per input message id.
Each result must include:
id, inbox_score (0..1), priority (0..1), label (HIGH|MEDIUM|LOW),
email_type, relationship_type, sender_type (PERSONAL|COMPANY|AUTOMATED|UNKNOWN),
intent, direct_human (boolean), requires_action (boolean), security_event (boolean),
security_reason, respond_recommended (boolean), reply_decision (DRAFT_REPLY|NO_REPLY|ASK_USER|ACTION_ONLY|WAIT),
risk (0..1), reason, priority_reason, confidence (0..1).

`reason` and `priority_reason` must be natural-language explanations suitable for the UI, not debug strings."""


DEEP_ANALYSIS_PROMPT = """You are the email-understanding layer of a high-quality communication assistant.
Read the complete message and available context like a careful human. Do not rely on keyword matching.
Determine what the message actually means, whether it is direct human communication or automation, what the sender expects, whether the user needs to act or reply, the relationship/tone, urgency, and any genuine safety/security concern.

Important distinctions:
- A company name containing 'security' is NOT a security incident.
- A personal email domain does NOT prove family/personal relationship.
- A university/job/recruiting word does NOT prove the message is direct work; distinguish bulk alerts from human communication.
- Automated mail can be important if it carries a real deadline, financial obligation, travel disruption, account incident, or required action.
- If the message does not need a reply, say so clearly.
- Never invent dates, decisions, availability, commitments, identities, or facts.

Return JSON only with:
priority (0..1), label (HIGH|MEDIUM|LOW), risk (0..1), intent, sender_type,
email_type, relationship_type, direct_human, requires_action, security_event,
security_reason, respond_recommended, reply_decision, reason, priority_reason,
urgency, known_facts, unknown_facts, confidence.
The `reason` must be a plain-English explanation for the user."""


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _normalize_item(raw: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    label = str(raw.get("label") or "LOW").upper()
    if label not in {"HIGH", "MEDIUM", "LOW"}:
        score = _safe_float(raw.get("priority"))
        label = "HIGH" if score >= 0.72 else "MEDIUM" if score >= 0.42 else "LOW"

    decision = str(raw.get("reply_decision") or ("DRAFT_REPLY" if raw.get("respond_recommended") else "NO_REPLY")).upper()
    if decision not in {"DRAFT_REPLY", "NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"}:
        decision = "NO_REPLY"

    out = {
        "id": raw.get("id") or fallback.get("id"),
        "inbox_score": _safe_float(raw.get("inbox_score"), _safe_float(raw.get("priority"))),
        "priority": _safe_float(raw.get("priority")),
        "label": label,
        "email_type": str(raw.get("email_type") or "UNKNOWN").upper(),
        "relationship_type": str(raw.get("relationship_type") or "UNKNOWN").upper(),
        "sender_type": str(raw.get("sender_type") or "UNKNOWN").upper(),
        "intent": str(raw.get("intent") or "general").lower(),
        "direct_human": bool(raw.get("direct_human")),
        "requires_action": bool(raw.get("requires_action")),
        "security_event": bool(raw.get("security_event")),
        "security_reason": str(raw.get("security_reason") or "").strip(),
        "respond_recommended": bool(raw.get("respond_recommended")),
        "reply_decision": decision,
        "risk": _safe_float(raw.get("risk")),
        "reason": str(raw.get("reason") or raw.get("priority_reason") or "AI triage completed.").strip(),
        "priority_reason": str(raw.get("priority_reason") or raw.get("reason") or "").strip(),
        "confidence": _safe_float(raw.get("confidence"), 0.5),
    }
    if out["security_event"] is False:
        out["security_reason"] = ""
    return out


def triage_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One compact OpenAI call ranks a candidate inbox batch semantically."""
    if not messages:
        return []

    max_candidates = int(os.getenv("INBOX_TRIAGE_MAX_CANDIDATES", "40"))
    selected = messages[:max_candidates]
    payload = []
    for message in selected:
        payload.append({
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "from": _clip(message.get("from"), 220),
            "subject": _clip(message.get("subject"), 280),
            "snippet": _clip(message.get("snippet"), 700),
            "timestamp": message.get("ts"),
            "source_folder": message.get("source_folder"),
            "labels": message.get("labelIds") or [],
            "has_attachments": bool(message.get("attachments")),
            "attachment_names": [_clip(a.get("filename"), 120) for a in (message.get("attachments") or [])[:3]],
        })

    provider = get_ai_provider()
    response = provider.generate_json(
        system=TRIAGE_SYSTEM_PROMPT,
        user={"messages": payload},
        max_tokens=int(os.getenv("INBOX_TRIAGE_MAX_TOKENS", "2400")),
        temperature=0.0,
    )
    returned = response.get("items") if isinstance(response, dict) else None
    by_id = {}
    for item in returned or []:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item

    normalized = []
    for original in selected:
        raw = by_id.get(str(original.get("id")), {})
        normalized.append(_normalize_item(raw, original))
    return normalized


def analyze_message_semantics(email: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    provider = get_ai_provider()
    response = provider.generate_json(
        system=DEEP_ANALYSIS_PROMPT,
        user={
            "message": {
                "id": email.get("id"),
                "thread_id": email.get("threadId"),
                "from": _clip(email.get("from"), 300),
                "to": _clip(email.get("to"), 300),
                "subject": _clip(email.get("subject"), 500),
                "body": _clip(email.get("body") or email.get("snippet"), 9000),
                "timestamp": email.get("ts"),
                "source_folder": email.get("source_folder"),
                "has_attachments": bool(email.get("attachments")),
                "attachments": [
                    {
                        "filename": a.get("filename"),
                        "file_type": a.get("file_type"),
                        "risk_level": a.get("risk_level"),
                    }
                    for a in (email.get("attachments") or [])[:3]
                ],
            },
            "prior_triage": existing or {},
        },
        max_tokens=int(os.getenv("EMAIL_ANALYSIS_MAX_TOKENS", "900")),
        temperature=0.0,
    )
    normalized = _normalize_item(response if isinstance(response, dict) else {}, email)
    normalized.update({
        "urgency": str((response or {}).get("urgency") or "normal"),
        "known_facts": (response or {}).get("known_facts") or [],
        "unknown_facts": (response or {}).get("unknown_facts") or [],
    })
    return normalized
