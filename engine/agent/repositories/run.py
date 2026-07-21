"""Run/Turn state transitions and atomic terminal response persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventProjector, RuntimeEventType
from engine.agent.repositories.evidence import EvidenceRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.response import ComposedResponse
from engine.agent.run import RunStatus, SessionLeaseConflict, TERMINAL_RUN_STATUSES
from engine.agent.session import SessionInputStatus, SessionLease
from engine.agent.turn import ModelTurnResult
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentSessionMemory,
    AgentTurn,
)
from engine.security.audit import SecurityAuditService


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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
        self.sessions.append_user_command_event(
            session_id=str(run.session_id),
            event_type=RuntimeEventType.RUN_CANCELLING,
            run_id=str(run.id),
            payload={"run": {"id": str(run.id), "status": run.status, "version": run.version}},
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
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.RUN_CANCELLED,
            run_id=str(run.id),
            payload={"run": {"id": str(run.id), "status": run.status, "version": run.version}},
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
        turn.reasoning_summary = result.reasoning_summary
        turn.tool_calls_json = _json([item.model_dump(mode="json") for item in result.tool_calls])
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
        if error_code:
            message = self.session.get(AgentMessage, run.assistant_message_id)
            if message is not None:
                message.content = ""
                message.status = "created"
                message.updated_at = _utcnow()
        run.version = int(run.version or 0) + 1
        run.updated_at = _utcnow()
        self.session.flush()
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.TURN_COMPLETED,
            run_id=str(run.id),
            turn_id=str(turn.id),
            payload={
                "turn": {
                    "id": str(turn.id),
                    "sequence": int(turn.sequence),
                    "status": str(turn.status),
                    "reasoning_summary": str(turn.reasoning_summary or ""),
                    "tool_call_count": len(result.tool_calls),
                    "usage": result.usage,
                }
            },
        )

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
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.ACTIVITY_UPDATED,
            run_id=run_id,
            payload={"activity": {
                "id": f"activity:{run_id}:repair:{run.repair_attempt_count}",
                "kind": "analysis",
                "title": "继续完善分析",
                "summary": reason,
                "status": "running",
                "missing": missing,
            }},
        )
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
            self.sessions.append_event(
                lease=lease,
                event_type=RuntimeEventType.ACTIVITY_UPDATED,
                run_id=run_id,
                turn_id=str(turn.id),
                payload={"activity": {
                    "id": f"activity:{turn.id}:analysis",
                    "kind": "recovery",
                    "title": "已恢复中断的分析",
                    "summary": "上次模型响应未完整结算，已从持久状态重新继续。",
                    "status": "failed",
                    "started_at": turn.created_at.isoformat() if turn.created_at else None,
                    "completed_at": now.isoformat(),
                }},
            )
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
    ) -> None:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        self._require_lease(run, lease)
        message = self.session.get(AgentMessage, run.assistant_message_id)
        if message is None:
            raise RuntimeError("Run has no assistant message draft")
        message.content = content
        message.status = "streaming"
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
        previous = state.get("progress") if isinstance(state.get("progress"), dict) else {}
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
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.ACTIVITY_UPDATED,
            run_id=run_id,
            payload={"activity": {
                "id": f"activity:{run_id}:progress",
                "kind": "analysis",
                "title": "已停止重复尝试",
                "summary": "连续多轮没有产生新的可验证结果，已基于当前证据结束本次分析。",
                "status": "completed",
            }},
        )

    @staticmethod
    def _working_result(run: AgentRun) -> dict[str, Any]:
        try:
            value = json.loads(str(run.result_json or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
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
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.ANSWER_COMPLETED,
            run_id=str(run.id),
            turn_id=str(run.current_turn_id) if run.current_turn_id else None,
            payload=RuntimeEventProjector.entity("response", response),
        )
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.RUN_COMPLETED,
            run_id=str(run.id),
            payload={"run": {
                "id": str(run.id),
                "status": run.status,
                "version": run.version,
                "completion_disposition": response.completion_disposition.value,
                "limitation_codes": [code.value for code in response.limitation_codes],
            }},
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
            assistant.status = "failed"
            assistant.updated_at = now
        if admitted is not None:
            admitted.status = SessionInputStatus.CONSUMED.value
            admitted.consumed_at = now
        self.session.flush()
        self.sessions.append_event(
            lease=lease,
            event_type=RuntimeEventType.RUN_FAILED,
            run_id=run_id,
            payload={"run": {"id": run_id, "status": run.status, "version": run.version},
                     "error": {"code": error_code, "message": message}},
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
                loaded = json.loads(str(row.memory_json or "{}"))
                previous = loaded if isinstance(loaded, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                previous = {}
        recent_runs = list(previous.get("recent_runs") or [])
        recent_runs.append({
            "run_id": str(run.id),
            "question": str(run.question or "")[:1_000],
            "answer_summary": response.answer.text[:1_200],
            "referenced_artifact_ids": response.referenced_artifact_ids,
            "completed_at": _utcnow().isoformat(),
        })
        memory = {
            "version": 1,
            "recent_runs": recent_runs[-8:],
            "working_set": {
                "selected_artifact_id": (
                    response.selection_suggestion.artifact_id
                    if response.selection_suggestion else aggregate.selected_artifact_id
                ),
                "referenced_artifact_ids": response.referenced_artifact_ids,
                "open_questions": response.answer.follow_up_questions[:5],
            },
            "stable_context": {
                **dict(previous.get("stable_context") or {}),
                **delta,
            },
        }
        if row is None:
            self.session.add(AgentSessionMemory(
                session_id=str(aggregate.id), datasource_id=str(aggregate.datasource_id),
                conversation_summary=response.answer.text[:2_000], memory_json=_json(memory),
            ))
        else:
            row.conversation_summary = response.answer.text[:2_000]
            row.memory_json = _json(memory)
            row.updated_at = _utcnow()
        aggregate.context_epoch = int(aggregate.context_epoch or 0) + 1

    @staticmethod
    def _require_lease(run: AgentRun, lease: SessionLease) -> None:
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise SessionLeaseConflict("Run is fenced by a different Session lease")
