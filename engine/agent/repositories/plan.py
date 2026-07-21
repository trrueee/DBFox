"""Task Plan settlement under the owning Session lease."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventProjector, RuntimeEventType
from engine.agent.plan import PlanStatus, PlanStep, PlanStepStatus, TaskPlan
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.models import AgentArtifactRecord, AgentRun, AgentTaskPlanRecord


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)

    def update(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        objective: str,
        steps: list[PlanStep],
        summary: str | None,
    ) -> TaskPlan:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise ValueError("Task Plan update is outside the active Session lease")
        self._validate_artifacts(lease.session_id, run_id, steps)
        row = self.session.execute(
            select(AgentTaskPlanRecord).where(AgentTaskPlanRecord.run_id == run_id).with_for_update()
        ).scalar_one_or_none()
        now = _utcnow()
        status = self._status(steps)
        if row is None:
            row = AgentTaskPlanRecord(
                id=f"plan_{uuid4().hex}",
                session_id=lease.session_id,
                run_id=run_id,
                turn_id=turn_id,
                version=1,
                objective=objective,
                steps_json=json.dumps([step.model_dump(mode="json") for step in steps], ensure_ascii=False),
                status=status.value,
                summary=summary,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.turn_id = turn_id
            row.version = int(row.version or 0) + 1
            row.objective = objective
            row.steps_json = json.dumps([step.model_dump(mode="json") for step in steps], ensure_ascii=False)
            row.status = status.value
            row.summary = summary
            row.updated_at = now
        self.session.flush()
        plan = self._domain(row)
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.PLAN_UPDATED,
            run_id=run_id,
            turn_id=turn_id,
            payload=RuntimeEventProjector.entity("plan", plan),
        )
        return plan

    def _validate_artifacts(self, session_id: str, run_id: str, steps: list[PlanStep]) -> None:
        artifact_ids = {artifact_id for step in steps for artifact_id in step.artifact_ids}
        if not artifact_ids:
            return
        rows = self.session.execute(
            select(AgentArtifactRecord.id).where(
                AgentArtifactRecord.session_id == session_id,
                AgentArtifactRecord.run_id == run_id,
                AgentArtifactRecord.id.in_(artifact_ids),
            )
        ).scalars().all()
        missing = artifact_ids - {str(value) for value in rows}
        if missing:
            raise ValueError(f"Task Plan references unavailable Artifacts: {', '.join(sorted(missing))}")

    @staticmethod
    def _status(steps: list[PlanStep]) -> PlanStatus:
        if all(step.status in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED} for step in steps):
            return PlanStatus.COMPLETED
        if any(step.status is PlanStepStatus.BLOCKED for step in steps):
            return PlanStatus.BLOCKED
        return PlanStatus.ACTIVE

    @staticmethod
    def _domain(row: AgentTaskPlanRecord) -> TaskPlan:
        return TaskPlan(
            id=str(row.id),
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            version=int(row.version),
            objective=str(row.objective),
            steps=[PlanStep.model_validate(value) for value in json.loads(str(row.steps_json or "[]"))],
            status=PlanStatus(str(row.status)),
            summary=str(row.summary) if row.summary else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
