from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Optional, Sequence

from openai import OpenAI


class AIProviderError(RuntimeError):
    """Raised when the hosted AI provider is unavailable, truncated, or misconfigured."""


class OpenAIProvider:
    """Single hosted AI provider used by the production application.

    Critical structured decisions use JSON Schema when supplied.  If the configured
    model/provider rejects json_schema, the call is retried once with json_object.
    Truncated completions are never parsed as if they were valid decisions.
    """

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise AIProviderError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=api_key)
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.reasoning_model = os.getenv("OPENAI_REASONING_MODEL", self.default_model).strip()
        self.vision_model = os.getenv("OPENAI_VISION_MODEL", self.default_model).strip()
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

    @staticmethod
    def _usage(response: Any, model: str) -> Dict[str, Any]:
        usage = getattr(response, "usage", None)
        if not usage:
            return {"model": model}
        return {
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "model": model,
        }

    @staticmethod
    def _decode_json(content: str) -> Dict[str, Any]:
        raw = (content or "").strip()
        if not raw:
            raise AIProviderError("OpenAI returned an empty structured response")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                f"OpenAI returned invalid/truncated JSON at char {exc.pos}: {exc.msg}"
            ) from exc
        if not isinstance(data, dict):
            raise AIProviderError("OpenAI structured response was not a JSON object")
        return data

    def generate_json(
        self,
        *,
        system: str,
        user: Dict[str, Any],
        max_tokens: int = 900,
        temperature: float = 0.2,
        use_reasoning_model: bool = False,
        schema: Dict[str, Any] | None = None,
        schema_name: str = "structured_result",
    ) -> Dict[str, Any]:
        model = self.reasoning_model if use_reasoning_model else self.default_model
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False, default=str)},
        ]

        formats: list[Dict[str, Any]] = []
        if schema:
            formats.append(
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name[:64],
                        "strict": True,
                        "schema": schema,
                    },
                }
            )
        formats.append({"type": "json_object"})

        last_exc: Exception | None = None
        for response_format in formats:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    messages=messages,
                )
                choice = response.choices[0]
                finish_reason = str(getattr(choice, "finish_reason", "") or "")
                if finish_reason == "length":
                    raise AIProviderError(
                        f"OpenAI structured response was truncated at max_tokens={max_tokens}"
                    )
                message = choice.message
                refusal = getattr(message, "refusal", None)
                if refusal:
                    raise AIProviderError(f"OpenAI refused the structured request: {refusal}")
                data = self._decode_json(message.content or "")
                data["_usage"] = self._usage(response, model)
                return data
            except AIProviderError:
                raise
            except Exception as exc:
                last_exc = exc
                # json_schema is intentionally allowed to fall back once to json_object
                # for a model/API configuration that does not support strict schema.
                if response_format.get("type") == "json_schema":
                    continue
                break

        raise AIProviderError(f"OpenAI request failed: {last_exc}") from last_exc

    def generate_json_with_images(
        self,
        *,
        system: str,
        user_text: str,
        image_data_urls: Sequence[str],
        max_tokens: int = 1400,
        temperature: float = 0.0,
        schema: Dict[str, Any] | None = None,
        schema_name: str = "vision_result",
    ) -> Dict[str, Any]:
        """Understand/OCR a small number of image pages using the hosted model.

        Used only when native text extraction/Tesseract did not produce meaningful
        text, which makes scanned PDFs/images work on Render without requiring a
        system Tesseract binary.
        """
        content: list[Dict[str, Any]] = [{"type": "text", "text": user_text}]
        for url in list(image_data_urls)[:3]:
            if url:
                content.append({"type": "image_url", "image_url": {"url": url, "detail": "high"}})

        formats: list[Dict[str, Any]] = []
        if schema:
            formats.append(
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name[:64],
                        "strict": True,
                        "schema": schema,
                    },
                }
            )
        formats.append({"type": "json_object"})

        last_exc: Exception | None = None
        for response_format in formats:
            try:
                response = self.client.chat.completions.create(
                    model=self.vision_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                )
                choice = response.choices[0]
                if str(getattr(choice, "finish_reason", "") or "") == "length":
                    raise AIProviderError("OpenAI vision/OCR response was truncated")
                data = self._decode_json(choice.message.content or "")
                data["_usage"] = self._usage(response, self.vision_model)
                return data
            except AIProviderError:
                raise
            except Exception as exc:
                last_exc = exc
                if response_format.get("type") == "json_schema":
                    continue
                break
        raise AIProviderError(f"OpenAI vision request failed: {last_exc}") from last_exc

    @staticmethod
    def bytes_to_data_url(data: bytes, mime_type: str = "image/jpeg") -> str:
        return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"

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
            choice = response.choices[0]
            if str(getattr(choice, "finish_reason", "") or "") == "length":
                raise AIProviderError(f"OpenAI text response truncated at max_tokens={max_tokens}")
            return (choice.message.content or "").strip()
        except AIProviderError:
            raise
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
