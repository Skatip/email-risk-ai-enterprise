from typing import List, Optional
from app.llm_clients import openai_embed


def embed_text(text: str) -> Optional[List[float]]:
    return openai_embed(text)
