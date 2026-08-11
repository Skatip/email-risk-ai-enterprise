from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from app.communication_brain.orchestrator import process_communication


def draft_reply(
    email: Dict[str, Any],
    analysis: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Backward-compatible reply entry point backed by the unified brain."""
    result = process_communication(email, analysis or {}, force=force)
    return {
        "sender": (email.get("from") or "").strip(),
        "reply": result.get("reply") or result.get("text") or "",
        "tone": result.get("tone") or "natural",
        "confidence": float(result.get("confidence") or 0.0),
        "decision": result.get("decision"),
        "clarification_question": result.get("clarification_question") or "",
        "suggested_actions": result.get("suggested_actions") or [],
        "commitments": result.get("commitments") or [],
        "follow_up": result.get("follow_up") or {},
        "reply_meta": {
            "strategy": "unified_communication_brain",
            "model": ((result.get("_usage") or {}).get("model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
            "force": bool(force),
            "suppressed": result.get("decision") == "NO_REPLY",
            "needs_user_input": result.get("decision") == "ASK_USER",
            "verified": bool((result.get("loop") or {}).get("verified")),
        },
        "meta": result,
    }


def save_rag_example(inbound: str, outbound: str, label: str = "style", user_id: str = "") -> Dict[str, Any]:
    """Save user-approved reply feedback through the PostgreSQL memory table."""
    inbound = (inbound or "").strip()
    outbound = (outbound or "").strip()
    if not inbound or not outbound:
        return {"ok": False, "error": "inbound and outbound required"}

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {"ok": False, "error": "DATABASE_URL is required"}

    import psycopg
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS reply_feedback_memory(
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT,
                    inbound_text TEXT NOT NULL,
                    approved_reply TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at BIGINT NOT NULL
                )"""
            )
            cur.execute(
                "INSERT INTO reply_feedback_memory(user_id,inbound_text,approved_reply,label,created_at) VALUES(%s,%s,%s,%s,%s)",
                (user_id or "", inbound, outbound, label or "style", int(time.time())),
            )
        conn.commit()
    return {"ok": True, "stored": True}


def load_reply_memories(user_id: str, limit: int = 3) -> list[Dict[str, Any]]:
    """Load a few recent user-approved replies as compact style memory."""
    if not user_id or not os.getenv("DATABASE_URL", "").strip():
        return []
    import psycopg
    from psycopg.rows import dict_row
    try:
        with psycopg.connect(os.getenv("DATABASE_URL"), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS reply_feedback_memory(
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT,
                    inbound_text TEXT NOT NULL,
                    approved_reply TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at BIGINT NOT NULL
                )""")
                cur.execute(
                    "SELECT inbound_text, approved_reply, label FROM reply_feedback_memory WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
                    (user_id, int(limit)),
                )
                rows = cur.fetchall()
        return [
            {
                "memory_type": "approved_reply_style",
                "inbound_example": str(r["inbound_text"] or "")[:900],
                "approved_reply": str(r["approved_reply"] or "")[:900],
                "label": r["label"],
            }
            for r in rows
        ]
    except Exception:
        return []
