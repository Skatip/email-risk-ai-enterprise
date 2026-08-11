from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List

from app.ai.provider import get_ai_provider
from app.db import connect

BUNDLE_PROMPT = """You are the multi-document understanding layer for an email communication assistant.
You are given structured intelligence for every attachment in one email. Understand them together as one case.
Do not merely concatenate summaries. Identify how the documents relate to the sender's request, what facts are shared or conflicting, what actions/deadlines matter, and what the reply must account for.
Never invent facts that are not present in the attachment analyses.
Return JSON only with: summary, key_facts, conflicts, action_items, deadlines, reply_context, priority_reason, confidence.
Keep reply_context compact and directly useful to the Communication Brain."""


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def _ensure_table() -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS attachment_intelligence_cache(
        user_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        filename TEXT,
        result JSONB NOT NULL,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        PRIMARY KEY(user_id, content_hash)
    )""")
    conn.commit(); conn.close()


def get_cached_attachment(user_id: str, sha256: str) -> Dict[str, Any] | None:
    if not user_id or not sha256:
        return None
    _ensure_table()
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT result FROM attachment_intelligence_cache WHERE user_id=? AND content_hash=?", (user_id, sha256))
    row = cur.fetchone(); conn.close()
    if not row:
        return None
    value = row.get("result") if isinstance(row, dict) else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    return value if isinstance(value, dict) else None


def save_cached_attachment(user_id: str, sha256: str, filename: str, result: Dict[str, Any]) -> None:
    if not user_id or not sha256:
        return
    _ensure_table()
    now = int(time.time())
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO attachment_intelligence_cache(user_id,content_hash,filename,result,created_at,updated_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id,content_hash) DO UPDATE SET filename=EXCLUDED.filename,result=EXCLUDED.result,updated_at=EXCLUDED.updated_at""",
        (user_id, sha256, filename or "", json.dumps(result), now, now),
    )
    conn.commit(); conn.close()


def aggregate_attachment_intelligence(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    clean = [r for r in (results or []) if isinstance(r, dict)]
    if not clean:
        return {
            "summary": "No attachment intelligence available.",
            "key_facts": [],
            "conflicts": [],
            "action_items": [],
            "deadlines": [],
            "reply_context": "",
            "priority_reason": "",
            "confidence": 0.0,
            "documents": [],
        }

    compact_docs = []
    for r in clean[:8]:
        compact_docs.append({
            "filename": r.get("filename"),
            "document_type": r.get("document_type"),
            "title": r.get("title"),
            "summary": str(r.get("summary") or "")[:1000],
            "key_details": (r.get("key_details") or [])[:10],
            "action_items": (r.get("action_items") or [])[:8],
            "dates": (r.get("dates") or [])[:8],
            "amounts": (r.get("amounts") or [])[:8],
            "ids": (r.get("ids") or [])[:8],
            "business_value": str(r.get("business_value") or "")[:500],
            "priority_reason": str(r.get("priority_reason") or "")[:350],
            "reply_context": str(r.get("reply_context") or "")[:700],
            "confidence": r.get("document_confidence") or r.get("confidence"),
        })

    if len(compact_docs) == 1:
        r = compact_docs[0]
        return {
            "summary": r.get("summary") or "Attachment analyzed.",
            "key_facts": r.get("key_details") or [],
            "conflicts": [],
            "action_items": r.get("action_items") or [],
            "deadlines": r.get("dates") or [],
            "reply_context": r.get("reply_context") or r.get("summary") or "",
            "priority_reason": r.get("priority_reason") or "",
            "confidence": float(r.get("confidence") or 0.0),
            "documents": clean,
        }

    provider = get_ai_provider()
    try:
        response = provider.generate_json(
            system=BUNDLE_PROMPT,
            user={"documents": compact_docs},
            max_tokens=int(os.getenv("ATTACHMENT_BUNDLE_MAX_TOKENS", "800")),
            temperature=0.0,
        )
    except Exception:
        response = {}

    if not isinstance(response, dict):
        response = {}

    fallback_context = "\n".join(
        f"{d.get('filename')}: {d.get('reply_context') or d.get('summary') or ''}" for d in compact_docs
    )[:3500]
    return {
        "summary": str(response.get("summary") or f"Analyzed {len(clean)} attachments together.")[:1400],
        "key_facts": (response.get("key_facts") or [])[:20],
        "conflicts": (response.get("conflicts") or [])[:10],
        "action_items": (response.get("action_items") or [])[:15],
        "deadlines": (response.get("deadlines") or [])[:12],
        "reply_context": str(response.get("reply_context") or fallback_context)[:4000],
        "priority_reason": str(response.get("priority_reason") or "")[:500],
        "confidence": max(0.0, min(1.0, float(response.get("confidence") or 0.65))),
        "documents": clean,
    }
