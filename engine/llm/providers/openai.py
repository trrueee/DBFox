"""OpenAI-compatible provider (covers OpenAI / Qwen / DeepSeek / local)."""
from __future__ import annotations

from typing import Any
from langchain_openai import ChatOpenAI


def create_openai_client(
    *,
    model_name: str,
    api_key: str,
    api_base: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout: float = 120.0,
) -> ChatOpenAI:
    """Build a ChatOpenAI client with reasoning-model awareness."""
    model_lower = model_name.lower()
    is_reasoning = any(
        term in model_lower
        for term in ("o1", "o3", "r1", "reasoner", "reasoning", "qwq")
    )

    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": api_key,
        "base_url": api_base,
        "timeout": timeout,
        "max_retries": 0,
    }

    if not is_reasoning:
        kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

    return ChatOpenAI(**kwargs)
