"""Lightweight agent run state tracker — carries steps and artifacts across
the ReAct loop lifecycle.  The authoritative graph state is DBFoxAgentState
(TypedDict); this model exists only for the service layer to accumulate
results for the final AgentRunResponse.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.agent_core.types import AgentArtifact, AgentStep


class AgentState(BaseModel):
    run_id: str
    session_id: str | None = None
    parent_run_id: str | None = None
    question: str
    datasource_id: str

    artifacts: list[AgentArtifact] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
