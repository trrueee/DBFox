"""DBFox LLM Infrastructure — provider-agnostic model access.

Dependency rule:
    engine.llm has NO internal project dependencies.
    It is consumed by agent, semantic, sql, and evaluation layers.
"""

from engine.llm.config import (
    LlmConfig,
    LlmConfigurationError,
    resolve_product_llm_config_from_credential,
)
from engine.llm.factory import LlmCallOptions, create_chat_model
from engine.llm.structured import with_structured_output

__all__ = [
    "LlmCallOptions",
    "LlmConfig",
    "LlmConfigurationError",
    "create_chat_model",
    "resolve_product_llm_config_from_credential",
    "with_structured_output",
]
