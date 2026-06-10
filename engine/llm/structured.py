"""Structured output helpers for LLM calls."""
from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def with_structured_output(model: Any, schema: type[T]) -> Any:
    """Wrap a chat model with structured output for a Pydantic schema.

    Thin wrapper so callers don't hard-code LangChain's
    ``model.with_structured_output()`` API directly.
    """
    return model.with_structured_output(schema)
