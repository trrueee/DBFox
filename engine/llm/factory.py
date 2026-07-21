"""LLM client factory - single entry point for model client construction."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

from engine.llm.config import LlmConfig
from engine.llm.providers.openai import create_openai_compatible_api_client


def create_openai_compatible_client(
    config: LlmConfig,
    *,
    timeout: float = 120.0,
) -> "OpenAI":
    """Build a non-LangChain OpenAI-compatible client through the LLM boundary.

    This is intentionally the only factory API for product code that needs
    direct SDK access.  Provider-level endpoint validation and transport
    ownership are therefore shared with the Agent model factory.
    """

    return create_openai_compatible_api_client(
        api_key=config.api_key,
        api_base=config.api_base,
        timeout=timeout,
    )
