"""Durable detection of meaningful Agent progress."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.json_codec import JsonCodecError, canonical_dumps as _canonical, loads
from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentTaskPlanRecord,
    AgentToolInvocation,
)


def _load(value: Any, fallback: Any) -> Any:
    try:
        loaded = loads(str(value))
    except JsonCodecError:
        return fallback
    return loaded


_VOLATILE_KEYS = {
    "createdat",
    "updatedat",
    "executedat",
    "observedat",
    "latencyms",
    "durationms",
    "executiontimems",
}


def _meaningful(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _meaningful(item)
            for key, item in value.items()
            if (
                str(key).replace("_", "").lower() not in _VOLATILE_KEYS
                and not str(key).replace("_", "").lower().endswith("id")
                and not str(key).replace("_", "").lower().endswith("ids")
            )
        }
    if isinstance(value, list):
        return [_meaningful(item) for item in value]
    return value


def observation_evidence_signatures(
    *,
    tool_name: str,
    status: str,
    facts: dict[str, Any],
    error_code: str,
) -> set[str]:
    """Project one typed observation onto durable, domain-neutral evidence."""

    base = {
        "tool": tool_name,
        "status": status,
        "error_code": error_code,
    }
    return {_canonical({**base, "facts": _meaningful(facts)})}


class ProgressGuard:
    """Build a restart-safe fingerprint without counting record churn as work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def fingerprint(self, run_id: str) -> str:
        artifacts = (
            self.session.execute(
                select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run_id)
            )
            .scalars()
            .all()
        )
        artifact_signatures = {
            _canonical(
                {
                    "type": str(row.type),
                    "title": str(row.title),
                    "status": str(row.status),
                    "summary": str(row.summary or ""),
                    "payload": _meaningful(_load(row.payload_json, {})),
                }
            )
            for row in artifacts
            if str(_load(row.presentation_json, {}).get("visibility") or "primary")
            == "primary"
        }

        observations = self.session.execute(
            select(AgentObservationRecord, AgentToolInvocation)
            .join(
                AgentToolInvocation,
                AgentToolInvocation.id == AgentObservationRecord.tool_invocation_id,
            )
            .where(AgentObservationRecord.run_id == run_id)
        ).all()
        observation_signatures: set[str] = set()
        for observation, invocation in observations:
            if not bool(observation.contributes_progress):
                continue
            facts = _load(observation.facts_json, {})
            observation_signatures.update(
                observation_evidence_signatures(
                    tool_name=str(invocation.tool_name),
                    status=str(observation.status),
                    facts=facts if isinstance(facts, dict) else {},
                    error_code=str(observation.error_code or ""),
                )
            )

        plan = self.session.execute(
            select(AgentTaskPlanRecord).where(AgentTaskPlanRecord.run_id == run_id)
        ).scalar_one_or_none()
        plan_state = (
            None
            if plan is None
            else {
                "objective": str(plan.objective),
                "steps": _meaningful(_load(plan.steps_json, [])),
                "status": str(plan.status),
                "summary": str(plan.summary or ""),
            }
        )
        state = {
            "artifacts": sorted(artifact_signatures),
            "observations": sorted(observation_signatures),
            "plan": plan_state,
        }
        return hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest()
