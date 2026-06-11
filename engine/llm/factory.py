"""LLM client factory — single entry point for all model access."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI

from engine.llm.providers.openai import create_openai_client


@dataclass
class LLMClientFactory:
    """Immutable factory bound to a specific provider config."""

    model_name: str
    api_key: str
    api_base: str

    def build(
        self,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> ChatOpenAI:
        return create_openai_client(
            model_name=self.model_name,
            api_key=self.api_key,
            api_base=self.api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )


def get_chat_model(
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout: float = 120.0,
) -> ChatOpenAI:
    """Build a ChatOpenAI client from explicit args, falling back to env vars.

    This is the single entry point for ALL LLM access in the DataBox engine.
    """
    key = (
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DATABOX_LLM_API_KEY")
        or ""
    ).strip()
    base = (
        api_base or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    ).strip()
    model = (
        model_name or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
    ).strip()

    return create_openai_client(
        model_name=model,
        api_key=key,
        api_base=base,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
