"""Run/Turn state transitions and atomic terminal response persistence."""

from __future__ import annotations
import logging
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
    MessageItem,
    MessagePayload,
    RunItemStatus,
    RunItemType,
    final_answer_item,
    dump_run_item,
    evidence_reference,
    project_run,
)
from engine.agent.session import DeliveryMode, SessionInputStatus, SessionLease
from engine.agent.turn import ModelTurnResult, TurnAssistantMessage, TurnTermination
from engine.json_codec import JsonCodecError, canonical_dumps as _json, loads
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentSessionMemory,
    AgentTurn,
    AgentRunItemRecord,
)
from engine.security.audit import SecurityAuditService

logger = logging.getLogger("dbfox.agent.run")


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

    def has_pending_steering_inputs(self, *, lease: SessionLease, run_id: str) -> bool:
        """Check the successful-terminalization barrier under the Run lock."""

        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        pending = self.session.execute(
            select(AgentSessionInput.id)
            .where(
                AgentSessionInput.run_id == run_id,
                AgentSessionInput.delivery_mode == DeliveryMode.STEER.value,
                AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
            )
            .limit(1)
        ).scalar_one_or_none()
        return pending is not None

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
                    payload={
                        "item": dump_run_item(final_answer_item(assistant, run=run))
                    },
                )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_CANCELLED,
            run_id=str(run.id),
            payload={"run": project_run(run)},
        )
        self.session.flush()

    def cancel_active_turns(self, *, lease: SessionLease, run_id: str) -> int:
        """Settle every open model Turn before its Run becomes cancelled."""

        return self._terminalize_active_turns(
            lease=lease,
            run_id=run_id,
            status="cancelled",
            termination=TurnTermination.CANCELLED,
            error_code=None,
            error_message=None,
        )

    def fail_active_turns(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        error_code: str,
        error_message: str,
    ) -> int:
        """Settle every open model Turn before its Run becomes failed."""

        return self._terminalize_active_turns(
            lease=lease,
            run_id=run_id,
            status="failed",
            termination=TurnTermination.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def _terminalize_active_turns(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        status: Literal["cancelled", "failed"],
        termination: TurnTermination,
        error_code: str | None,
        error_message: str | None,
    ) -> int:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        turns = (
            self.session.execute(
                select(AgentTurn)
                .where(
                    AgentTurn.run_id == run_id,
                    AgentTurn.status == "running",
                )
                .order_by(AgentTurn.sequence)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        if not turns:
            return 0

        now = _utcnow()
        for turn in turns:
            self._cancel_in_progress_turn_messages(
                lease=lease,
                run_id=run_id,
                turn=turn,
                now=now,
            )
            turn.status = status
            turn.termination = termination.value
            turn.error_code = error_code
            turn.error_message = error_message
            turn.completed_at = now

        run.current_turn_id = None
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        return len(turns)

    def _cancel_in_progress_turn_messages(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn: AgentTurn,
        now: datetime,
    ) -> None:
        active_messages = (
            self.session.execute(
                select(AgentRunItemRecord)
                .where(
                    AgentRunItemRecord.turn_id == str(turn.id),
                    AgentRunItemRecord.item_type == RunItemType.MESSAGE.value,
                    AgentRunItemRecord.status == RunItemStatus.IN_PROGRESS.value,
                )
                .order_by(AgentRunItemRecord.sequence)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for record in active_messages:
            item = MessageItem.model_validate(loads(str(record.item_json or "{}")))
            cancelled = item.model_copy(
                update={
                    "revision": int(item.revision) + 1,
                    "status": RunItemStatus.CANCELLED,
                    "completed_at": now,
                }
            )
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=run_id,
                turn_id=str(turn.id),
                payload={"item": dump_run_item(cancelled)},
            )

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
        turn.reasoning_summary = result.reasoning_summary
        turn.tool_calls_json = _json(
            [item.model_dump(mode="json") for item in result.tool_calls]
        )
        turn.response_items_json = _json(result.output_items)
        turn.usage_json = _json(result.usage)
        turn.termination = result.termination.value if result.termination else None
        turn.error_code = error_code
        turn.error_message = error_message
        turn.status = "failed" if error_code else "completed"
        turn.completed_at = _utcnow()
        run.consumed_input_tokens = int(run.consumed_input_tokens or 0) + max(
            0, input_tokens
        )
        run.consumed_output_tokens = int(run.consumed_output_tokens or 0) + max(
            0, output_tokens
        )
        run.consumed_tokens = int(run.consumed_tokens or 0) + max(0, total_tokens)
        run.consumed_cost_usd = float(run.consumed_cost_usd or 0.0) + max(0.0, cost_usd)
        if error_code and error_code.startswith("MODEL_PROVIDER_"):
            run.provider_retry_count = int(run.provider_retry_count or 0) + 1
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()

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
        turns = (
            self.session.execute(
                select(AgentTurn)
                .where(
                    AgentTurn.run_id == run_id,
                    AgentTurn.status == "running",
                )
                .order_by(AgentTurn.sequence)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        if not turns:
            return 0
        now = _utcnow()
        for turn in turns:
            self._cancel_in_progress_turn_messages(
                lease=lease,
                run_id=run_id,
                turn=turn,
                now=now,
            )
            turn.status = "failed"
            turn.error_code = "MODEL_STREAM_INTERRUPTED"
            turn.error_message = "模型响应在完成前中断，Runtime 已从持久状态继续。"
            turn.reasoning_summary = "上次模型响应未完整结算，已从持久状态重新继续。"
            turn.completed_at = now
            run.provider_retry_count = int(run.provider_retry_count or 0) + 1
        run.current_turn_id = None
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        return len(turns)

    def persist_turn_message(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        output_index: int,
        revision: int,
        phase: Literal["commentary", "final_answer"] | None,
        content: str,
        status: RunItemStatus,
    ) -> str:
        """Persist one provider-neutral assistant message as its own RunItem."""

        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        if str(run.current_turn_id or "") != turn_id:
            raise ValueError("Turn message is outside the active Run Turn")
        item_id = f"message:{run_id}:{turn_id}:{output_index}"
        existing = self.session.get(AgentRunItemRecord, item_id)
        now = _utcnow()
        created_at = existing.created_at if existing is not None else now
        completed_at = (
            now
            if status
            in {
                RunItemStatus.COMPLETED,
                RunItemStatus.FAILED,
                RunItemStatus.CANCELLED,
            }
            else None
        )
        item = MessageItem(
            type=RunItemType.MESSAGE,
            id=item_id,
            session_id=lease.session_id,
            run_id=run_id,
            turn_id=turn_id,
            revision=revision,
            status=status,
            created_at=created_at,
            completed_at=completed_at,
            payload=MessagePayload(
                role="assistant",
                phase=phase,
                content=content,
            ),
        )
        event_type = {
            RunItemStatus.IN_PROGRESS: (
                RuntimeEventType.RUN_ITEM_UPDATED
                if existing is not None
                else RuntimeEventType.RUN_ITEM_STARTED
            ),
            RunItemStatus.COMPLETED: RuntimeEventType.RUN_ITEM_COMPLETED,
            RunItemStatus.FAILED: RuntimeEventType.RUN_ITEM_FAILED,
            RunItemStatus.CANCELLED: RuntimeEventType.RUN_ITEM_CANCELLED,
        }.get(status)
        if event_type is None:
            raise ValueError(f"Unsupported Turn message status: {status}")
        self.sessions.events.append(
            lease=lease,
            event_type=event_type,
            run_id=run_id,
            turn_id=turn_id,
            payload={"item": dump_run_item(item)},
        )
        self.session.flush()
        return item_id

    def latest_completed_answer(self, run_id: str) -> ModelTurnResult:
        """Restore the latest eligible answer from canonical Turn and RunItem state."""

        turn = self.session.execute(
            select(AgentTurn)
            .where(
                AgentTurn.run_id == run_id,
                AgentTurn.status == "completed",
                AgentTurn.error_code.is_(None),
                AgentTurn.tool_calls_json == "[]",
                AgentTurn.termination == TurnTermination.COMPLETED.value,
            )
            .order_by(AgentTurn.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if turn is None:
            return ModelTurnResult()
        prefix = f"message:{run_id}:{turn.id}:"
        records = (
            self.session.execute(
                select(AgentRunItemRecord)
                .where(
                    AgentRunItemRecord.run_id == run_id,
                    AgentRunItemRecord.turn_id == str(turn.id),
                    AgentRunItemRecord.item_type == RunItemType.MESSAGE.value,
                    AgentRunItemRecord.status == RunItemStatus.COMPLETED.value,
                )
                .order_by(AgentRunItemRecord.sequence)
            )
            .scalars()
            .all()
        )
        messages: list[TurnAssistantMessage] = []
        for record in records:
            if not str(record.id).startswith(prefix):
                continue
            output_index_text = str(record.id)[len(prefix) :]
            if not output_index_text.isdigit():
                continue
            item = MessageItem.model_validate(loads(str(record.item_json or "{}")))
            if item.payload.role != "assistant":
                continue
            messages.append(
                TurnAssistantMessage(
                    item_id=str(record.id),
                    output_index=int(output_index_text),
                    phase=item.payload.phase,
                    status="completed",
                    text=item.payload.content,
                )
            )
        return ModelTurnResult(
            turn_id=str(turn.id),
            messages=messages,
            reasoning_summary=str(turn.reasoning_summary or ""),
            termination=TurnTermination.COMPLETED,
        )

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
        terminal_turn_id: str | None = None,
        terminal_output_index: int | None = None,
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
            select(AgentSession)
            .where(AgentSession.id == run.session_id)
            .with_for_update()
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
        terminal_item: MessageItem | None = None
        if terminal_output_index is not None and terminal_turn_id:
            terminal_item_id = (
                f"message:{run.id}:{terminal_turn_id}:{terminal_output_index}"
            )
            terminal_record = self.session.get(AgentRunItemRecord, terminal_item_id)
            if terminal_record is None:
                raise RuntimeError("Terminal assistant RunItem is missing")
            loaded_item = loads(str(terminal_record.item_json or "{}"))
            validated_terminal_item = MessageItem.model_validate(loaded_item)
            terminal_item = validated_terminal_item.model_copy(
                update={
                    "revision": int(validated_terminal_item.revision) + 1,
                    "status": RunItemStatus.COMPLETED,
                    "completed_at": now,
                    "payload": validated_terminal_item.payload.model_copy(
                        update={
                            "evidence": [
                                evidence_reference(value)
                                for value in response.answer.evidence
                            ],
                            "artifact_refs": [
                                ArtifactReference(artifact_id=artifact_id)
                                for artifact_id in response.referenced_artifact_ids
                            ],
                            "completion_disposition": response.completion_disposition,
                            "limitation_codes": list(response.limitation_codes),
                        }
                    ),
                }
            )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=str(run.id),
            turn_id=terminal_turn_id,
            payload={
                "item": dump_run_item(
                    terminal_item
                    if terminal_item is not None
                    else final_answer_item(
                        message,
                        run=run,
                        evidence=[
                            evidence_reference(value)
                            for value in response.answer.evidence
                        ],
                        artifact_refs=[
                            ArtifactReference(artifact_id=artifact_id)
                            for artifact_id in response.referenced_artifact_ids
                        ],
                    )
                )
            },
        )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_COMPLETED,
            run_id=str(run.id),
            payload={"run": project_run(run)},
        )

    def fail(
        self, *, lease: SessionLease, run_id: str, error_code: str, message: str
    ) -> None:
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
            select(AgentSessionMemory).where(
                AgentSessionMemory.session_id == aggregate.id
            )
        ).scalar_one_or_none()
        previous: dict[str, Any] = {}
        if row is not None:
            try:
                loaded = loads(str(row.memory_json or "{}"))
                previous = loaded if isinstance(loaded, dict) else {}
            except JsonCodecError:
                previous = {}
        previous_stable = dict(previous.get("stable_context") or {})
        previous_evidence = [
            item
            for item in list(previous_stable.pop("evidence_references", []))
            if isinstance(item, dict)
            and item.get("artifact_id")
        ]
        # Legacy model-authored verified_claims remain inert in old records.
        # Citation establishes provenance, not the truth of the model's prose.
        previous_stable.pop("verified_claims", None)
        incoming_evidence = [
            dict(item)
            for item in list(delta.get("evidence_references") or [])
            if isinstance(item, dict) and item.get("artifact_id")
        ]
        evidence_by_key = {
            str(item["artifact_id"]): item
            for item in [*previous_evidence, *incoming_evidence]
        }
        stable_delta = {
            key: value
            for key, value in delta.items()
            if key not in {"verified_claims", "evidence_references"}
        }
        memory = {
            "version": 1,
            "working_set": {
                "selected_artifact_id": (
                    response.selection_suggestion.artifact_id
                    if response.selection_suggestion
                    else aggregate.selected_artifact_id
                ),
                "referenced_artifact_ids": response.referenced_artifact_ids,
                "open_questions": response.answer.follow_up_questions[:5],
            },
            "stable_context": {
                **previous_stable,
                **stable_delta,
                "evidence_references": list(evidence_by_key.values())[-32:],
            },
        }
        if row is None:
            self.session.add(
                AgentSessionMemory(
                    session_id=str(aggregate.id),
                    memory_json=_json(memory),
                )
            )
        else:
            row.memory_json = _json(memory)
            row.updated_at = _utcnow()
        aggregate.context_epoch = int(aggregate.context_epoch or 0) + 1
        self.session.flush()

    @staticmethod
    def _require_lease(run: AgentRun, lease: SessionLease) -> None:
        if (
            str(run.session_id) != lease.session_id
            or int(run.lease_token or 0) != lease.token
        ):
            raise SessionLeaseConflict("Run is fenced by a different Session lease")
