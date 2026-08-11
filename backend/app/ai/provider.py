from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from openai import OpenAI


class AIProviderError(RuntimeError):
    """Raised when the hosted AI provider is unavailable or misconfigured."""


class OpenAIProvider:
    """Single hosted AI provider used by the production application."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise AIProviderError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=api_key)
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.reasoning_model = os.getenv("OPENAI_REASONING_MODEL", self.default_model).strip()
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

    def generate_json(
        self,
        *,
        system: str,
        user: Dict[str, Any],
        max_tokens: int = 900,
        temperature: float = 0.2,
        use_reasoning_model: bool = False,
    ) -> Dict[str, Any]:
        model = self.reasoning_model if use_reasoning_model else self.default_model
        try:
            response = self.client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False, default=str)},
                ],
            )
            data = json.loads((response.choices[0].message.content or "{}").strip())
            if getattr(response, "usage", None):
                data["_usage"] = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "model": model,
                }
            return data
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

    def generate_text(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.3,
        use_reasoning_model: bool = False,
    ) -> str:
        model = self.reasoning_model if use_reasoning_model else self.default_model
        try:
            response = self.client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

    def embed(self, text: str) -> Optional[list[float]]:
        clean = (text or "").strip()
        if not clean:
            return None
        try:
            result = self.client.embeddings.create(model=self.embedding_model, input=clean[:12000])
            return list(result.data[0].embedding)
        except Exception as exc:
            raise AIProviderError(f"OpenAI embedding request failed: {exc}") from exc


_provider: OpenAIProvider | None = None


def get_ai_provider() -> OpenAIProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIProvider()
    return _provider
