from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from app.llm_clients import openai_embed

RAG_DB_PATH = "postgresql://communication_memory"


def embed_text(text: str) -> Optional[List[float]]:
    return openai_embed(" ".join((text or "").split()))


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) ** 2 for x in a))
    nb = math.sqrt(sum(float(y) ** 2 for y in b))
    return dot / ((na * nb) or 1.0)


def retrieve_examples(query_text: str, k: int = 4, max_scan: int = 200, min_score: float = 0.28) -> List[Dict[str, Any]]:
    url = os.getenv("DATABASE_URL", "").strip()
    vector = embed_text(query_text)
    if not url or not vector:
        return []
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS reply_style_examples(
                id BIGSERIAL PRIMARY KEY, user_id TEXT DEFAULT '', inbox_text TEXT NOT NULL,
                outbox_text TEXT NOT NULL, meta_json JSONB DEFAULT '{}'::jsonb,
                inbox_embedding JSONB, created_at BIGINT)""")
            cur.execute("SELECT * FROM reply_style_examples ORDER BY created_at DESC LIMIT %s", (max_scan,))
            rows = cur.fetchall()
    scored = []
    for row in rows:
        candidate = row.get("inbox_embedding") or []
        score = _cosine(vector, candidate) if candidate else 0.0
        if score >= min_score:
            scored.append({"inbox": row["inbox_text"], "outbox": row["outbox_text"], "meta": row.get("meta_json") or {}, "score": score})
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:k]
