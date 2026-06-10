from __future__ import annotations

import os
from typing import Any
from langchain_openai import ChatOpenAI


def get_chat_model(
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout: float = 30.0,
) -> ChatOpenAI:
    key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    base = (api_base or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")).strip()
    model = (model_name or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")).strip()

    model_lower = model.lower()
    is_reasoning = any(term in model_lower for term in ("o1", "o3", "r1", "reasoner", "reasoning", "qwq"))

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": key,
        "base_url": base,
        "timeout": timeout,
    }

    if not is_reasoning:
        kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

    return ChatOpenAI(**kwargs)
