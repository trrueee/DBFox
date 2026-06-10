"""DataBox Agent Runtime — public API.

This package is the Agent Runtime layer.  It exports:
  - DataBoxAgentRuntime  — the facade for running agents
  - DataBoxAgentService  — the LangGraph ReAct engine
  - build_databox_react_graph — graph builder

For types and contracts, import from engine.agent_core.
For tools, import from engine.tools.
"""

from __future__ import annotations

from engine.agent.runtime import DataBoxAgentRuntime
from engine.agent.app.service import DataBoxAgentService
from engine.agent.graph.react_graph import build_databox_react_graph

__all__ = [
    "DataBoxAgentRuntime",
    "DataBoxAgentService",
    "build_databox_react_graph",
]
