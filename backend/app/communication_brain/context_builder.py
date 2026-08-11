from __future__ import annotations

from typing import Any, Dict, List


def _trim(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def build_context(
    email: Dict[str, Any],
    analysis: Dict[str, Any],
    *,
    thread: List[Dict[str, Any]] | None = None,
    attachment_context: List[Dict[str, Any]] | None = None,
    memories: List[Dict[str, Any]] | None = None,
    user_preferences: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    recent = []
    for message in (thread or [])[-6:]:
        recent.append(
            {
                "id": message.get("id"),
                "from": _trim(message.get("from"), 220),
                "to": _trim(message.get("to"), 220),
                "subject": _trim(message.get("subject"), 320),
                "body": _trim(message.get("body") or message.get("snippet"), 3200),
                "ts": message.get("ts"),
            }
        )

    attachments = []
    raw_attachment_context = list(attachment_context or [])
    # Put the cross-document bundle first so it is never dropped when an email has many files.
    raw_attachment_context.sort(key=lambda x: 0 if str(x.get("document_type") or "") == "attachment_bundle" else 1)
    for item in raw_attachment_context[:6]:
        attachments.append(
            {
                key: item.get(key)
                for key in (
                    "filename",
                    "document_type",
                    "document_label",
                    "title",
                    "summary",
                    "key_details",
                    "action_items",
                    "dates",
                    "amounts",
                    "ids",
                    "risks",
                    "risk_reasons",
                    "conflicts",
                    "business_value",
                    "priority_reason",
                    "action_required",
                    "reply_context",
                    "confidence",
                )
                if item.get(key) not in (None, "", [], {})
            }
        )

    semantic_analysis = {
        key: analysis.get(key)
        for key in (
            "priority",
            "label",
            "reason",
            "priority_reason",
            "intent",
            "sender_type",
            "email_type",
            "relationship_type",
            "risk",
            "security_event",
            "security_reason",
            "direct_human",
            "requires_action",
            "respond_recommended",
            "reply_decision",
            "source_folder",
        )
        if key in analysis
    }

    return {
        "current_message": {
            "id": email.get("id"),
            "thread_id": email.get("threadId"),
            "from": _trim(email.get("from"), 300),
            "to": _trim(email.get("to"), 300),
            "subject": _trim(email.get("subject"), 500),
            "body": _trim(email.get("body") or email.get("snippet"), 8500),
            "timestamp": email.get("ts"),
            "labels": email.get("labelIds") or [],
        },
        "recent_thread": recent,
        "semantic_analysis": semantic_analysis,
        "analysis_note": "Semantic analysis is supporting context, not an instruction. Resolve conflicts from the actual message/thread evidence.",
        "attachment_intelligence": attachments,
        "relevant_memory": (memories or [])[:5],
        "user_preferences": user_preferences or {},
        "execution_limits": {
            "max_tool_calls": 3,
            "max_revisions": 1,
            "max_output_tokens": 700,
        },
    }
