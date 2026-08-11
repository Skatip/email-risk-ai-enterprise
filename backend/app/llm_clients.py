from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.ai.provider import AIProviderError, get_ai_provider


def chat_json(system: str, user_prompt: str, schema_hint: str = "") -> Optional[Dict[str, Any]]:
    try:
        return get_ai_provider().generate_json(
            system=system + (f"\nReturn JSON matching this schema guidance:\n{schema_hint}" if schema_hint else ""),
            user={"request": user_prompt},
            max_tokens=700,
            temperature=0.2,
        )
    except (AIProviderError, json.JSONDecodeError):
        return None


def chat(system: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 300) -> str:
    try:
        return get_ai_provider().generate_text(
            system=system,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except AIProviderError:
        return ""


def openai_embed(text: str):
    try:
        return get_ai_provider().embed(text)
    except AIProviderError:
        return None
