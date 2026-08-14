"""Task Plan settlement under the owning Session lease."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventType
from engine.agent.plan import PlanStatus, PlanStep, PlanStepStatus, TaskPlan
from engine.agent.run_item import dump_run_item, plan_item
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.json_codec import canonical_dumps, load_array
from engine.models import AgentArtifactRecord, AgentRun, AgentTaskPlanRecord


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PlanArtifactUnavailableError(ValueError):
    """A Task Plan referenced an Artifact unavailable to the current Run."""


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
        if (
            str(run.session_id) != lease.session_id
            or int(run.lease_token or 0) != lease.token
        ):
            raise ValueError("Task Plan update is outside the active Session lease")
        self._validate_artifacts(lease.session_id, run_id, steps)
        row = self.session.execute(
            select(AgentTaskPlanRecord)
            .where(AgentTaskPlanRecord.run_id == run_id)
            .with_for_update()
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
                steps_json=canonical_dumps(steps),
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
            row.steps_json = canonical_dumps(steps)
            row.status = status.value
            row.summary = summary
            row.updated_at = now
        self.session.flush()
        plan = self._domain(row)
        self.sessions.events.append(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_STARTED
                if int(row.version) == 1
                else (
                    RuntimeEventType.RUN_ITEM_COMPLETED
                    if status is PlanStatus.COMPLETED
                    else RuntimeEventType.RUN_ITEM_UPDATED
                )
            ),
            run_id=run_id,
            turn_id=turn_id,
            payload={"item": dump_run_item(plan_item(row))},
        )
        return plan

    def terminalize(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        status: PlanStatus,
        summary: str | None = None,
    ) -> TaskPlan | None:
        if status in {PlanStatus.ACTIVE, PlanStatus.BLOCKED}:
            raise ValueError("Task Plan terminal status is required")
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if (
            str(run.session_id) != lease.session_id
            or int(run.lease_token or 0) != lease.token
        ):
            raise ValueError(
                "Task Plan terminalization is outside the active Session lease"
            )
        row = self.session.execute(
            select(AgentTaskPlanRecord)
            .where(AgentTaskPlanRecord.run_id == run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return None
        current_status = PlanStatus(str(row.status))
        if current_status in {
            PlanStatus.COMPLETED,
            PlanStatus.PARTIAL,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }:
            return self._domain(row)

        steps = [
            self._terminal_step(PlanStep.model_validate(value), status)
            for value in load_array(str(row.steps_json or "[]"))
        ]
        now = _utcnow()
        row.version = int(row.version or 0) + 1
        row.steps_json = canonical_dumps(steps)
        row.status = status.value
        row.summary = summary or self._terminal_summary(status)
        row.updated_at = now
        self.session.flush()
        plan = self._domain(row)
        self.sessions.events.append(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_CANCELLED
                if status is PlanStatus.CANCELLED
                else (
                    RuntimeEventType.RUN_ITEM_FAILED
                    if status is PlanStatus.FAILED
                    else RuntimeEventType.RUN_ITEM_COMPLETED
                )
            ),
            run_id=run_id,
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(plan_item(row))},
        )
        return plan

    def _validate_artifacts(
        self, session_id: str, run_id: str, steps: list[PlanStep]
    ) -> None:
        artifact_ids = {
            artifact_id for step in steps for artifact_id in step.artifact_ids
        }
        if not artifact_ids:
            return
        rows = (
            self.session.execute(
                select(AgentArtifactRecord.id).where(
                    AgentArtifactRecord.session_id == session_id,
                    AgentArtifactRecord.run_id == run_id,
                    AgentArtifactRecord.id.in_(artifact_ids),
                )
            )
            .scalars()
            .all()
        )
        available_ids = {str(value) for value in rows}
        available_ids.update(
            artifact.id
            for artifact in ArtifactRepository(self.session).referenced_results_for_run(
                run_id
            )
        )
        missing = artifact_ids - available_ids
        if missing:
            raise PlanArtifactUnavailableError(
                "Task Plan references unavailable Artifacts: "
                + ", ".join(sorted(missing))
            )

    @staticmethod
    def _status(steps: list[PlanStep]) -> PlanStatus:
        if all(
            step.status in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
            for step in steps
        ):
            return PlanStatus.COMPLETED
        if any(step.status is PlanStepStatus.BLOCKED for step in steps):
            return PlanStatus.BLOCKED
        return PlanStatus.ACTIVE

    @staticmethod
    def _terminal_step(step: PlanStep, status: PlanStatus) -> PlanStep:
        if step.status not in {PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS}:
            return step
        if status is PlanStatus.FAILED and step.status is PlanStepStatus.IN_PROGRESS:
            return step.model_copy(
                update={
                    "status": PlanStepStatus.BLOCKED,
                    "note": step.note or "运行失败，当前步骤未能完成。",
                }
            )
        return step.model_copy(
            update={
                "status": PlanStepStatus.SKIPPED,
                "note": step.note
                or {
                    PlanStatus.COMPLETED: "运行已完成，此步骤不再需要。",
                    PlanStatus.PARTIAL: "运行以部分结果结束，此步骤未继续执行。",
                    PlanStatus.CANCELLED: "运行已取消，此步骤未继续执行。",
                    PlanStatus.FAILED: "运行失败，此步骤未执行。",
                }[status],
            }
        )

    @staticmethod
    def _terminal_summary(status: PlanStatus) -> str:
        return {
            PlanStatus.COMPLETED: "分析计划已随运行完成。",
            PlanStatus.PARTIAL: "分析计划以部分结果结束。",
            PlanStatus.FAILED: "分析计划因运行失败而终止。",
            PlanStatus.CANCELLED: "分析计划已取消。",
        }[status]

    @staticmethod
    def _domain(row: AgentTaskPlanRecord) -> TaskPlan:
        return TaskPlan(
            id=str(row.id),
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            version=int(row.version),
            objective=str(row.objective),
            steps=[
                PlanStep.model_validate(value)
                for value in load_array(str(row.steps_json or "[]"))
            ],
            status=PlanStatus(str(row.status)),
            summary=str(row.summary) if row.summary else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
