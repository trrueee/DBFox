"""Run/Turn state transitions and atomic terminal response persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventType
from engine.agent.repositories.evidence import EvidenceRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.response import ComposedResponse
from engine.agent.run import RunStatus, SessionLeaseConflict, TERMINAL_RUN_STATUSES
from engine.agent.run_item import (
    ArtifactReference,
    final_answer_item,
    assistant_message_item,
    dump_run_item,
    evidence_reference,
    project_run,
)
from engine.agent.session import SessionInputStatus, SessionLease
from engine.agent.turn import ModelTurnResult
from engine.json_codec import JsonCodecError, canonical_dumps as _json, loads
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentSessionMemory,
    AgentTurn,
)
from engine.security.audit import SecurityAuditService


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)
        self.evidence = EvidenceRepository(session)

    def get(self, run_id: str) -> AgentRun:
        run = self.session.get(AgentRun, run_id, populate_existing=True)
        if run is None:
            raise ValueError(f"Agent Run does not exist: {run_id}")
        return run

    def cancellation_requested(self, *, lease: SessionLease, run_id: str) -> bool:
        run = self.get(run_id)
        self._require_lease(run, lease)
        return bool(run.cancel_requested) or run.status in {
            RunStatus.CANCELLING.value,
            RunStatus.CANCELLED.value,
        }

    def request_cancel(self, *, run_id: str) -> AgentRun:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if RunStatus(str(run.status)) in TERMINAL_RUN_STATUSES:
            return run
        now = _utcnow()
        run.cancel_requested = True
        run.status = RunStatus.CANCELLING.value
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.sessions.events.append_user_command(
            session_id=str(run.session_id),
            event_type=RuntimeEventType.RUN_UPDATED,
            run_id=str(run.id),
            payload={"run": project_run(run)},
        )
        SecurityAuditService(self.session).record(
            action="agent.run.cancel",
            outcome="requested",
            resource_type="agent_run",
            resource_id=str(run.id),
            session_id=str(run.session_id),
            run_id=str(run.id),
            correlation_id=f"cancel:{run.id}:{run.version}",
        )
        self.session.flush()
        return run

    def cancel(self, *, lease: SessionLease, run_id: str) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        if run.status == RunStatus.CANCELLED.value:
            return
        admitted = self.session.get(AgentSessionInput, run.input_id)
        assistant = self.session.get(AgentMessage, run.assistant_message_id)
        now = _utcnow()
        run.status = RunStatus.CANCELLED.value
        run.version = int(run.version or 0) + 1
        run.completed_at = now
        run.updated_at = now
        if admitted is not None:
            admitted.status = SessionInputStatus.CANCELLED.value
            admitted.consumed_at = now
        if assistant is not None:
            assistant.status = "cancelled"
            assistant.updated_at = now
            if str(assistant.content or ""):
                self.sessions.events.append(
                    lease=lease,
                    event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                    run_id=str(run.id),
                    turn_id=str(run.current_turn_id) if run.current_turn_id else None,
                    payload={"item": dump_run_item(final_answer_item(assistant, run=run))},
                )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_CANCELLED,
            run_id=str(run.id),
            payload={"run": project_run(run)},
        )
        self.session.flush()

    def settle_turn(
        self,
        *,
        lease: SessionLease,
        turn_id: str,
        result: ModelTurnResult,
        error_code: str | None = None,
        error_message: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        begin_agent_write(self.session)
        turn = self.session.execute(
            select(AgentTurn).where(AgentTurn.id == turn_id).with_for_update()
        ).scalar_one()
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == turn.run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        if turn.status != "running":
            raise ValueError(f"Turn cannot settle from status {turn.status}")
        turn.draft_text = "" if error_code else result.text
        turn.message_phase = result.message_phase
        turn.reasoning_summary = result.reasoning_summary
        turn.tool_calls_json = _json([item.model_dump(mode="json") for item in result.tool_calls])
        turn.response_items_json = _json(result.output_items)
        turn.usage_json = _json(result.usage)
        turn.finish_signal = result.finish_signal
        turn.error_code = error_code
        turn.error_message = error_message
        turn.status = "failed" if error_code else "completed"
        turn.completed_at = _utcnow()
        run.consumed_input_tokens = int(run.consumed_input_tokens or 0) + max(0, input_tokens)
        run.consumed_output_tokens = int(run.consumed_output_tokens or 0) + max(0, output_tokens)
        run.consumed_tokens = int(run.consumed_tokens or 0) + max(0, total_tokens)
        run.consumed_cost_usd = float(run.consumed_cost_usd or 0.0) + max(0.0, cost_usd)
        if error_code and error_code.startswith("MODEL_PROVIDER_"):
            run.provider_retry_count = int(run.provider_retry_count or 0) + 1
        message = self.session.get(AgentMessage, run.assistant_message_id)
        discard_answer = bool(error_code)
        cancelled_answer: dict[str, Any] | None = None
        if discard_answer and message is not None and message.status == "streaming":
            message.status = "cancelled"
            message.updated_at = _utcnow()
            cancelled_answer = dump_run_item(final_answer_item(message, run=run))
        commentary_message: dict[str, Any] | None = None
        if (
            not error_code
            and result.tool_calls
            and message is not None
            and str(message.content or "").strip()
        ):
            message.status = "completed"
            message.updated_at = _utcnow()
            commentary_message = dump_run_item(
                assistant_message_item(
                    message,
                    run=run,
                    turn_id=str(turn.id),
                    phase="commentary",
                )
            )
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()
        if commentary_message is not None:
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_COMPLETED,
                run_id=str(run.id),
                turn_id=str(turn.id),
                payload={"item": commentary_message},
            )
            message.content = ""
            message.status = "created"
            message.updated_at = _utcnow()
        if cancelled_answer is not None:
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=str(run.id),
                turn_id=str(turn.id),
                payload={"item": cancelled_answer},
            )
            message.content = ""
            message.status = "created"
            message.updated_at = _utcnow()

    def record_repair(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        reason: str,
        missing: list[str],
    ) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        run.repair_attempt_count = int(run.repair_attempt_count or 0) + 1
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()

    def recover_interrupted_turns(self, *, lease: SessionLease, run_id: str) -> int:
        """Close model Turns left open by a stopped process before resuming the Run."""
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        turns = self.session.execute(
            select(AgentTurn).where(
                AgentTurn.run_id == run_id,
                AgentTurn.status == "running",
            ).order_by(AgentTurn.sequence).with_for_update()
        ).scalars().all()
        if not turns:
            return 0
        now = _utcnow()
        for turn in turns:
            turn.status = "failed"
            turn.error_code = "MODEL_STREAM_INTERRUPTED"
            turn.error_message = "模型响应在完成前中断，Runtime 已从持久状态继续。"
            turn.reasoning_summary = "上次模型响应未完整结算，已从持久状态重新继续。"
            turn.completed_at = now
            run.provider_retry_count = int(run.provider_retry_count or 0) + 1
        message = self.session.get(AgentMessage, run.assistant_message_id)
        if message is not None and message.status == "streaming":
            message.content = ""
            message.status = "created"
            message.updated_at = now
        run.current_turn_id = None
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        return len(turns)

    def merge_answer_draft(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        content: str,
        phase: Literal["commentary", "final_answer"],
    ) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        message = self.session.get(AgentMessage, run.assistant_message_id)
        if message is None:
            raise RuntimeError("Run has no assistant message draft")
        is_new_item = message.status != "streaming"
        message.content = content
        message.status = "streaming"
        message.updated_at = _utcnow()
        self.session.flush()
        self.sessions.events.append(
            lease=lease,
            event_type=(
                RuntimeEventType.RUN_ITEM_STARTED
                if is_new_item
                else RuntimeEventType.RUN_ITEM_UPDATED
            ),
            run_id=run_id,
            turn_id=str(run.current_turn_id) if run.current_turn_id else None,
            payload={
                "item": dump_run_item(
                    assistant_message_item(
                        message,
                        run=run,
                        phase=phase,
                    )
                )
            },
        )

    def discard_answer_draft(self, *, lease: SessionLease, run_id: str) -> None:
        """Cancel a provisional answer that failed the completion gate."""

        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        message = self.session.get(AgentMessage, run.assistant_message_id)
        if message is None or message.status != "streaming":
            return
        message.status = "cancelled"
        message.updated_at = _utcnow()
        self.session.flush()
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
            run_id=run_id,
            turn_id=str(run.current_turn_id) if run.current_turn_id else None,
            payload={"item": dump_run_item(final_answer_item(message, run=run))},
        )
        message.content = ""
        message.status = "created"
        message.updated_at = _utcnow()
        self.session.flush()

    def record_focus(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        kind: str,
        reason: str,
        missing: list[str],
    ) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        state = self._working_result(run)
        state["focus"] = {"kind": kind, "reason": reason, "missing": missing}
        run.result_json = _json(state)
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()

    def record_progress(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        fingerprint: str,
    ) -> int:
        """Persist progress continuity so process restarts cannot reset the guard."""
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        state = self._working_result(run)
        progress = state.get("progress")
        previous = progress if isinstance(progress, dict) else {}
        stalled_turns = (
            int(previous.get("stalled_turns") or 0) + 1
            if previous.get("fingerprint") == fingerprint
            else 0
        )
        state["progress"] = {"fingerprint": fingerprint, "stalled_turns": stalled_turns}
        run.result_json = _json(state)
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()
        return stalled_turns

    def record_no_progress(self, *, lease: SessionLease, run_id: str) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        self.session.flush()

    @staticmethod
    def _working_result(run: AgentRun) -> dict[str, Any]:
        try:
            value = loads(str(run.result_json or "{}"))
        except JsonCodecError:
            return {}
        return value if isinstance(value, dict) else {}

    def complete(
        self,
        *,
        lease: SessionLease,
        response: ComposedResponse,
        memory_delta: dict[str, Any] | None = None,
    ) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == response.run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        if RunStatus(str(run.status)) in TERMINAL_RUN_STATUSES:
            raise ValueError(f"Run is already terminal: {run.status}")
        if bool(run.cancel_requested):
            raise ValueError("Cancelled Run cannot be completed")
        message = self.session.get(AgentMessage, run.assistant_message_id)
        admitted = self.session.get(AgentSessionInput, run.input_id)
        aggregate = self.session.execute(
            select(AgentSession).where(AgentSession.id == run.session_id).with_for_update()
        ).scalar_one()
        if message is None or admitted is None:
            raise RuntimeError("Run terminal projection is incomplete")

        self.evidence.add_all(
            session_id=str(run.session_id),
            run_id=str(run.id),
            evidence=response.answer.evidence,
        )
        now = _utcnow()
        message.content = response.answer.text
        message.status = "completed"
        message.updated_at = now
        admitted.status = SessionInputStatus.CONSUMED.value
        admitted.consumed_at = now
        run.status = RunStatus.COMPLETED.value
        run.version = int(run.version or 0) + 1
        run.result_json = _json(response.model_dump(mode="json"))
        run.completed_at = now
        run.updated_at = now

        if response.selection_suggestion and not aggregate.selected_artifact_id:
            aggregate.selected_artifact_id = response.selection_suggestion.artifact_id
        self._write_memory(aggregate, run, response, memory_delta or {})
        self.session.flush()
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=str(run.id),
            turn_id=str(run.current_turn_id) if run.current_turn_id else None,
            payload={"item": dump_run_item(final_answer_item(
                message,
                run=run,
                evidence=[evidence_reference(value) for value in response.answer.evidence],
                artifact_refs=[
                    ArtifactReference(artifact_id=artifact_id)
                    for artifact_id in response.referenced_artifact_ids
                ],
            ))},
        )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_COMPLETED,
            run_id=str(run.id),
            payload={"run": project_run(run)},
        )

    def fail(self, *, lease: SessionLease, run_id: str, error_code: str, message: str) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        if RunStatus(str(run.status)) in TERMINAL_RUN_STATUSES:
            return
        assistant = self.session.get(AgentMessage, run.assistant_message_id)
        admitted = self.session.get(AgentSessionInput, run.input_id)
        now = _utcnow()
        run.status = RunStatus.FAILED.value
        run.error_code = error_code
        run.error_message = message
        run.version = int(run.version or 0) + 1
        run.completed_at = now
        run.updated_at = now
        if assistant is not None:
            assistant.status = "cancelled" if str(assistant.content or "") else "failed"
            assistant.updated_at = now
        if admitted is not None:
            admitted.status = SessionInputStatus.CONSUMED.value
            admitted.consumed_at = now
        self.session.flush()
        if assistant is not None and str(assistant.content or ""):
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=run_id,
                turn_id=str(run.current_turn_id) if run.current_turn_id else None,
                payload={"item": dump_run_item(final_answer_item(assistant, run=run))},
            )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_FAILED,
            run_id=run_id,
            payload={"run": project_run(run)},
        )

    def _write_memory(
        self,
        aggregate: AgentSession,
        run: AgentRun,
        response: ComposedResponse,
        delta: dict[str, Any],
    ) -> None:
        row = self.session.execute(
            select(AgentSessionMemory).where(AgentSessionMemory.session_id == aggregate.id)
        ).scalar_one_or_none()
        previous: dict[str, Any] = {}
        if row is not None:
            try:
                loaded = loads(str(row.memory_json or "{}"))
                previous = loaded if isinstance(loaded, dict) else {}
            except JsonCodecError:
                previous = {}
        current_datasource_id = str(run.datasource_id)
        current_generation = int(run.datasource_generation)
        same_generation = (
            previous.get("datasource_id") == current_datasource_id
            and previous.get("datasource_generation") == current_generation
        )
        recent_runs = [
            item
            for item in list(previous.get("recent_runs") or [])
            if isinstance(item, dict)
            and item.get("datasource_id") == current_datasource_id
            and item.get("datasource_generation") == current_generation
        ]
        recent_runs.append({
            "run_id": str(run.id),
            "question": str(run.question or "")[:1_000],
            "answer_summary": response.answer.text[:1_200],
            "referenced_artifact_ids": response.referenced_artifact_ids,
            "datasource_id": current_datasource_id,
            "datasource_generation": current_generation,
            "completed_at": _utcnow().isoformat(),
        })
        recent_runs = recent_runs[-8:]
        previous_stable = (
            dict(previous.get("stable_context") or {})
            if same_generation
            else {}
        )
        previous_claims = [
            item
            for item in list(previous_stable.pop("verified_claims", []))
            if isinstance(item, dict)
            and item.get("claim_id")
            and item.get("datasource_id") == current_datasource_id
            and item.get("datasource_generation") == current_generation
        ]
        incoming_claims = [
            {
                **item,
                "datasource_id": current_datasource_id,
                "datasource_generation": current_generation,
            }
            for item in list(delta.get("verified_claims") or [])
            if isinstance(item, dict) and item.get("claim_id")
        ]
        claims_by_id = {
            str(item["claim_id"]): item
            for item in [*previous_claims, *incoming_claims]
        }
        stable_delta = {
            key: value
            for key, value in delta.items()
            if key != "verified_claims"
        }
        memory = {
            "version": 1,
            "datasource_id": current_datasource_id,
            "recent_runs": recent_runs,
            "working_set": {
                "datasource_id": current_datasource_id,
                "datasource_generation": current_generation,
                "selected_artifact_id": (
                    response.selection_suggestion.artifact_id
                    if response.selection_suggestion else aggregate.selected_artifact_id
                ),
                "referenced_artifact_ids": response.referenced_artifact_ids,
                "open_questions": response.answer.follow_up_questions[:5],
            },
            "stable_context": {
                **previous_stable,
                **stable_delta,
                "verified_claims": list(claims_by_id.values())[-32:],
            },
            "datasource_generation": current_generation,
        }
        if row is None:
            self.session.add(AgentSessionMemory(
                session_id=str(aggregate.id), datasource_id=str(aggregate.datasource_id),
                memory_json=_json(memory),
            ))
        else:
            row.memory_json = _json(memory)
            row.updated_at = _utcnow()
        aggregate.context_epoch = int(aggregate.context_epoch or 0) + 1

    @staticmethod
    def _require_lease(run: AgentRun, lease: SessionLease) -> None:
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Run is fenced by a different Session lease")
