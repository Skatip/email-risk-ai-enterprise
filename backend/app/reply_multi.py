from __future__ import annotations

import os
from typing import Any, Dict, List

from app.ai.provider import get_ai_provider
from app.communication_brain.context_builder import build_context


MULTI_PROMPT = """You generate optional alternative replies for the same grounded email situation.
Understand the supplied message, recent thread, attachment intelligence, and memory semantically.
Do not invent facts, dates, availability, commitments, attachments, decisions, or actions.
If the context says a reply is not appropriate or essential user information is missing, return an empty options array.
Otherwise return exactly three concise, natural alternatives that answer the same sender request, with slightly different tone/length while preserving facts.
Return JSON only: {"options": ["...", "...", "..."]}."""


def generate_multi(
    email: Dict[str, Any],
    analysis: Dict[str, Any],
    *,
    thread: List[Dict[str, Any]] | None = None,
    attachment_context: List[Dict[str, Any]] | None = None,
    memories: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    decision = str(analysis.get("reply_decision") or analysis.get("decision") or "").upper()
    if decision in {"NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"} or analysis.get("respond_recommended") is False:
        return {"options": [], "count": 0}

    context = build_context(email, analysis, thread=thread or [], attachment_context=attachment_context or [], memories=memories or [])
    provider = get_ai_provider()
    result = provider.generate_json(
        system=MULTI_PROMPT,
        user=context,
        max_tokens=int(os.getenv("MULTI_REPLY_MAX_TOKENS", "700")),
        temperature=0.3,
    )
    options = []
    for value in result.get("options") or []:
        text = str(value or "").strip()
        if text and text not in options:
            options.append(text)
        if len(options) >= 3:
            break
    return {"options": options, "count": len(options)}
