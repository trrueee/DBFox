from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.agent.app.runtime_registry import get_graph_runtime_registry
from engine.agent.graph.context import GraphRuntimeContext
from engine.agent_core.event_store import AgentEventStore
from engine.agent_core.types import AgentRunRequest
from engine.security.credential_vault import CredentialVault, get_credential_vault
from engine.tools.runtime.registry import ToolRegistry


class RequestContext:
    """Bundles a request with process-local graph dependencies.

    ``graph_config`` contains only opaque IDs.  Database sessions, tool
    registries, event stores, and vault access stay in the process-local
    runtime registry and therefore cannot be checkpointed.
    """

    def __init__(
        self,
        db: Session,
        request: AgentRunRequest,
        registry: ToolRegistry | None = None,
        event_store: AgentEventStore | None = None,
        credential_vault: CredentialVault | None = None,
    ) -> None:
        from engine.tools.dbfox_tools import register_dbfox_tools

        self.db = db
        self.request = request
        self.registry = registry or register_dbfox_tools()
        self.event_store = event_store
        self.credential_vault = credential_vault or get_credential_vault()

    def graph_config(self, thread_id: str, *, run_id: str | None = None) -> dict[str, Any]:
        """Build the safe LangGraph config for this in-process invocation."""
        runtime_context = GraphRuntimeContext(
            thread_id=thread_id,
            run_id=run_id or thread_id,
            runtime_id="",
            llm_credential_id=self.request.llm_credential_id,
            registry=self.registry,
            db=self.db,
            request=self.request,
            event_store=self.event_store,
            model_name=self.request.model_name,
            api_base=self.request.api_base,
            credential_vault=self.credential_vault,
        )
        registered_context = get_graph_runtime_registry().register(runtime_context)
        return {
            "configurable": registered_context.to_configurable(),
            "recursion_limit": max(self.request.max_steps * 4, 100),
        }

    def release_graph_config(self, config: dict[str, Any]) -> None:
        configurable = config.get("configurable")
        if isinstance(configurable, dict):
            runtime_id = configurable.get("runtime_id")
            if isinstance(runtime_id, str):
                get_graph_runtime_registry().discard(runtime_id)
