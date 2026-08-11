from __future__ import annotations
from typing import Dict, List
from app.llm_clients import chat


def generate_candidates(messages: List[Dict[str, str]], n: int = 3) -> List[str]:
    """Generate a small number of alternatives through the hosted provider.

    Kept for backward compatibility. The unified Communication Brain is the
    primary reply path; this helper is used only by the existing multi-reply UI.
    """
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "Write a natural email reply.")
    user = "\n".join(m.get("content", "") for m in messages if m.get("role") != "system")
    outputs: List[str] = []
    for temperature in (0.25, 0.45, 0.65)[: max(1, min(n, 3))]:
        value = chat(system, user, temperature=temperature, max_tokens=350).strip()
        if value and value not in outputs:
            outputs.append(value)
    return outputs
