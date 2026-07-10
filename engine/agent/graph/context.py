"""Typed process-local graph runtime context.

Only opaque identifiers are allowed in LangGraph's serializable
``configurable`` mapping. Graph nodes call :func:`graph_context` to recover
their in-process dependencies and resolve a credential just before an LLM
request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from engine.agent.app.runtime_registry import get_graph_runtime_registry
from engine.agent_core.event_store import AgentEventStore
from engine.agent_core.types import AgentRunRequest
from engine.errors import DBFoxError
from engine.llm.config import resolve_product_llm_config_from_credential
from engine.llm.factory import LlmCallOptions, create_chat_model as create_resolved_chat_model
from engine.security.credential_vault import CredentialVault
from engine.tools.runtime.registry import ToolRegistry


@dataclass(frozen=True)
class GraphRuntimeContext:
    """In-process dependencies for one Agent graph invocation."""

    thread_id: str
    run_id: str
    runtime_id: str
    llm_credential_id: str | None
    registry: ToolRegistry
    db: Session
    request: AgentRunRequest
    event_store: AgentEventStore | None = None
    model_name: str | None = None
    api_base: str | None = None
    credential_vault: CredentialVault | None = None

    def create_chat_model(self, options: LlmCallOptions | None = None) -> Any:
        """Construct a provider client without exposing a raw key to graph nodes."""
        if not self.llm_credential_id:
            raise DBFoxError("LLM credential is not configured.", code="NO_LLM_CREDENTIAL")
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=self.llm_credential_id,
            api_base=self.api_base,
            model_name=self.model_name,
            credential_vault=self.credential_vault,
        )
        return create_resolved_chat_model(config, options)

    @property
    def has_llm_credentials(self) -> bool:
        return self.llm_credential_id is not None

    def to_configurable(self) -> dict[str, Any]:
        """Return the only values allowed in a persisted RunnableConfig."""
        return {
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "runtime_id": self.runtime_id,
            "llm_credential_id": self.llm_credential_id,
        }


def graph_context(config: RunnableConfig) -> GraphRuntimeContext:
    """Resolve a typed in-process context from opaque config identifiers."""
    raw: dict[str, Any] = config.get("configurable") or {}
    runtime_id = str(raw["runtime_id"])
    context = get_graph_runtime_registry().get(runtime_id)
    if (
        context.thread_id != str(raw["thread_id"])
        or context.run_id != str(raw["run_id"])
        or context.llm_credential_id != raw.get("llm_credential_id")
    ):
        raise DBFoxError(
            "Graph runtime configuration does not match its registered context.",
            code="GRAPH_RUNTIME_CONTEXT_MISMATCH",
        )
    return context
