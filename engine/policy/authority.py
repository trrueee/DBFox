"""Immutable execution authority issued after a durable approval."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict

from engine.json_codec import canonical_dumps
from engine.resource import ResourceScopeRef


def canonical_hash(value: Any) -> str:
    encoded = canonical_dumps(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExecutionAuthority(BaseModel):
    """A verified grant bound to one invocation and one canonical action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    invocation_id: str
    tool_name: str
    authorized_input_hash: str
    policy_fingerprint: str
    approval_subject_fingerprint: str | None = None
    resource_ref: ResourceScopeRef | None = None

    def authorizes(
        self,
        *,
        tool_name: str,
        approval_subject: dict[str, Any],
        resource_ref: ResourceScopeRef | None,
    ) -> bool:
        return (
            self.tool_name == tool_name
            and self.approval_subject_fingerprint
            == canonical_hash(approval_subject)
            and self.resource_ref == resource_ref
        )
