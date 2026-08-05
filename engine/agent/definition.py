"""Versioned Agent identity and execution policy."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.run import RunLimits
from engine.json_codec import canonical_dumps


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "dbfox.data_analyst"
    version: str = "3.1"
    behavior: str = "autonomous_evidence_grounded_analysis"
    allowed_tool_groups: tuple[str, ...] = (
        "control",
        "conversation",
        "catalog",
        "query",
        "result",
    )
    execution_mode: str = "agent_autonomous_read"
    limits: RunLimits = Field(default_factory=RunLimits)

    @property
    def hash(self) -> str:
        value = canonical_dumps(self)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


DEFAULT_AGENT_DEFINITION = AgentDefinition()
