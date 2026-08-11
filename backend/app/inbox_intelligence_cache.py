from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable

from app.db import connect


SEMANTIC_CACHE_TTL_SECONDS = int(__import__("os").getenv("INBOX_SEMANTIC_CACHE_TTL_SECONDS", str(60 * 60 * 24 * 7)))  # inbox horizon is 7 days


def init_inbox_intelligence_cache() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS inbox_intelligence_cache(
            user_id TEXT NOT NULL,
            email_id TEXT NOT NULL,
            semantic_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at BIGINT NOT NULL,
            PRIMARY KEY(user_id, email_id)
        )"""
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_inbox_intelligence_user_updated ON inbox_intelligence_cache(user_id, updated_at DESC)"
    )
    conn.commit()
    conn.close()


def get_cached_semantics(user_id: str, email_ids: Iterable[str], max_age_seconds: int = SEMANTIC_CACHE_TTL_SECONDS) -> Dict[str, Dict[str, Any]]:
    ids = [str(x) for x in email_ids if x]
    if not ids:
        return {}
    cutoff = int(time.time()) - int(max_age_seconds)
    placeholders = ",".join(["?"] * len(ids))
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        f"SELECT email_id, semantic_json FROM inbox_intelligence_cache WHERE user_id=? AND updated_at>=? AND email_id IN ({placeholders})",
        (user_id or "", cutoff, *ids),
    )
    rows = cur.fetchall()
    conn.close()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        value = row.get("semantic_json") or {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                value = {}
        if isinstance(value, dict):
            out[str(row.get("email_id"))] = value
    return out


def save_semantics(user_id: str, semantics: Iterable[Dict[str, Any]]) -> None:
    now = int(time.time())
    conn = connect()
    cur = conn.cursor()
    for item in semantics or []:
        email_id = str(item.get("id") or "")
        if not email_id:
            continue
        cur.execute(
            """INSERT INTO inbox_intelligence_cache(user_id,email_id,semantic_json,updated_at)
               VALUES(?,?,?::jsonb,?)
               ON CONFLICT(user_id,email_id) DO UPDATE
               SET semantic_json=EXCLUDED.semantic_json, updated_at=EXCLUDED.updated_at""",
            (user_id or "", email_id, json.dumps(item), now),
        )
    conn.commit()
    conn.close()
