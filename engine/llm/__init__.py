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
from engine.llm.factory import create_openai_compatible_client
from engine.llm.structured import with_structured_output

__all__ = [
    "LlmConfig",
    "LlmConfigurationError",
    "create_openai_compatible_client",
    "resolve_product_llm_config_from_credential",
    "with_structured_output",
]
