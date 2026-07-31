"""Immutable execution authority issued after a durable approval."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict

from engine.json_codec import canonical_dumps


def canonical_hash(value: Any) -> str:
    encoded = canonical_dumps(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safety_fingerprint(safety: dict[str, Any]) -> str:
    return canonical_hash(safety)


class ExecutionAuthority(BaseModel):
    """A verified grant bound to one invocation and one canonical action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    invocation_id: str
    tool_name: str
    authorized_input_hash: str
    policy_fingerprint: str
    safety_fingerprint: str | None = None
    datasource_generation: int | None = None

    def authorizes_safety(
        self,
        *,
        tool_name: str,
        safety: dict[str, Any],
        datasource_generation: int | None,
    ) -> bool:
        return (
            self.tool_name == tool_name
            and self.safety_fingerprint == safety_fingerprint(safety)
            and self.datasource_generation == datasource_generation
        )
