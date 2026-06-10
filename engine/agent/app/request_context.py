from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentRunRequest, AgentRunResponse
from engine.agent_core.tool_registry import ToolRegistry
from engine.agent.app.runtime_config import RuntimeConfig


class RequestContext:
    """Bundles everything needed to run one agent invocation through the graph."""

    def __init__(
        self,
        db: Session,
        request: AgentRunRequest,
        registry: ToolRegistry | None = None,
    ):
        from engine.tools.databox_tools import register_databox_tools

        self.db = db
        self.request = request
        self.registry = registry or register_databox_tools()

        # Resolved model config (request overrides env)
        self.model_name = request.model_name
        self.api_key = request.api_key
        self.api_base = request.api_base

    def graph_config(self, thread_id: str) -> dict[str, Any]:
        """Build the LangGraph config dict passed to graph nodes via RunnableConfig."""
        configurable = {
            "thread_id": thread_id,
            "model_name": self.model_name,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "registry": self.registry,
            "db": self.db,
            "request": self.request,
        }
        return {
            "configurable": configurable,
            "recursion_limit": max(self.request.max_steps * 4, 100),
        }
