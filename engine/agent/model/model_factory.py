"""Deprecated — all LLM access now goes through engine.llm."""
from __future__ import annotations

from engine.llm import get_chat_model  # noqa: F401 — re-export for legacy callers
