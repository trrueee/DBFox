"""DBFox Agent Runtime — public API.

This package is the Agent Runtime layer.  It exports:
  - DBFoxAgentRuntime  — the facade for running agents
  - DBFoxAgentService  — the LangGraph ReAct engine
  - build_dbfox_react_graph — graph builder

For types and contracts, import from engine.agent_core.
For tools, import from engine.tools.
"""

from __future__ import annotations

from engine.agent.runtime import DBFoxAgentRuntime
from engine.agent.app.service import DBFoxAgentService
from engine.agent.graph.react_graph import build_dbfox_react_graph

__all__ = [
    "DBFoxAgentRuntime",
    "DBFoxAgentService",
    "build_dbfox_react_graph",
]
