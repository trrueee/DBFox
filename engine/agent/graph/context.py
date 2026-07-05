"""Typed graph runtime context — replaces the untyped configurable dict.

Every graph node MUST use ``graph_context(config)`` instead of
raw ``config.get("configurable") or {}``.  Missing required fields
raise immediately rather than silently producing None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from engine.agent_core.event_store import AgentEventStore
from engine.agent_core.types import AgentRunRequest
from engine.tools.runtime.registry import ToolRegistry


@dataclass(frozen=True)
class GraphRuntimeContext:
    """Immutable context injected into every graph node.

    All fields that are required for correct execution use bare attribute
    access (not .get()) so that a missing dependency fails fast at node
    entry, not deep inside a tool call or LLM invocation.
    """

    thread_id: str
    registry: ToolRegistry
    db: Session
    request: AgentRunRequest
    event_store: AgentEventStore | None = None
    model_name: str | None = None
    api_key: str | None = None
    api_base: str | None = None

    @property
    def has_llm_credentials(self) -> bool:
        """True when the request supplied an LLM API key."""
        return bool((self.api_key or "").strip())

    def to_configurable(self) -> dict[str, Any]:
        """Produce the legacy configurable dict (for LangGraph compatibility)."""
        return {
            "thread_id": self.thread_id,
            "model_name": self.model_name,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "registry": self.registry,
            "db": self.db,
            "request": self.request,
            "event_store": self.event_store,
        }


def graph_context(config: RunnableConfig) -> GraphRuntimeContext:
    """Extract a typed GraphRuntimeContext from a LangGraph RunnableConfig.

    Required fields (registry, db, request) use bare dict access so that
    a missing key raises KeyError immediately — no silent None propagation.
    """
    raw: dict[str, Any] = config.get("configurable") or {}
    return GraphRuntimeContext(
        thread_id=str(raw.get("thread_id", "")),
        registry=raw["registry"],
        db=raw["db"],
        request=raw["request"],
        event_store=raw.get("event_store"),
        model_name=raw.get("model_name"),
        api_key=raw.get("api_key"),
        api_base=raw.get("api_base"),
    )
