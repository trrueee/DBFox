"""Durable detection of meaningful Agent progress."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentTaskPlanRecord,
    AgentToolInvocation,
)


def _load(value: Any, fallback: Any) -> Any:
    try:
        loaded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return loaded


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


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


class ProgressGuard:
    """Build a restart-safe fingerprint without counting record churn as work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def fingerprint(self, run_id: str) -> str:
        artifacts = self.session.execute(
            select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run_id)
        ).scalars().all()
        artifact_signatures = {
            _canonical({
                "semantic_id": str(row.semantic_id or ""),
                "type": str(row.type),
                "title": str(row.title),
                "status": str(row.status),
                "summary": str(row.summary or ""),
                "payload": _meaningful(_load(row.payload_json, {})),
            })
            for row in artifacts
        }

        observations = self.session.execute(
            select(AgentObservationRecord, AgentToolInvocation)
            .join(AgentToolInvocation, AgentToolInvocation.id == AgentObservationRecord.tool_invocation_id)
            .where(AgentObservationRecord.run_id == run_id)
        ).all()
        observation_signatures = {
            _canonical({
                "tool": str(invocation.tool_name),
                "status": str(observation.status),
                "facts": _meaningful(_load(observation.facts_json, {})),
                "error_code": str(observation.error_code or ""),
            })
            for observation, invocation in observations
        }

        plan = self.session.execute(
            select(AgentTaskPlanRecord).where(AgentTaskPlanRecord.run_id == run_id)
        ).scalar_one_or_none()
        plan_state = None if plan is None else {
            "objective": str(plan.objective),
            "steps": _meaningful(_load(plan.steps_json, [])),
            "status": str(plan.status),
            "summary": str(plan.summary or ""),
        }
        state = {
            "artifacts": sorted(artifact_signatures),
            "observations": sorted(observation_signatures),
            "plan": plan_state,
        }
        return hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest()
