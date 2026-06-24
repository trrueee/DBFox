from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session


class AgentEventStore:
    def start_run(self, *args: Any, **kwargs: Any) -> None:
        pass

    def append_event(self, session_id: str, event: Any) -> None:
        pass

    def append_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        pass

    def create_approval(
        self,
        *,
        run_id: str,
        session_id: str,
        step_name: str,
        tool_name: str | None,
        risk_level: str,
        reason: str | None,
        policy_decision: dict[str, Any],
        requested_action: dict[str, Any] | None = None,
    ) -> Any | None:
        return None

    def save_checkpoint(
        self,
        *,
        run_id: str,
        session_id: str,
        status: str,
        current_step_name: str | None,
        next_step_name: str | None,
        plan: Any | None,
        state: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        pending_steps: list[dict[str, Any]],
        artifacts: list[dict[str, Any]] | None = None,
        waiting_approval_id: str | None = None,
    ) -> Any | None:
        return None

    def complete_run(self, response: Any) -> None:
        pass

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        pass

    def cancel_run(self, run_id: str) -> None:
        pass

    def resolve_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        decision: str,
        note: str | None = None,
    ) -> Any | None:
        return None

    def mark_run_resumed(self, run_id: str, current_step_name: str | None = "query_database") -> None:
        pass

    def flush(self) -> None:
        pass


class NoopAgentEventStore(AgentEventStore):
    pass


def _request_with_session_id(req: Any, session_id: str) -> Any:
    if getattr(req, "session_id", None) == session_id:
        return req
    if hasattr(req, "model_copy"):
        return req.model_copy(update={"session_id": session_id})
    try:
        req.session_id = session_id
    except Exception:
        pass
    return req


class SQLiteAgentEventStore(AgentEventStore):
    def __init__(self, db: Session) -> None:
        self.db = db

    def start_run(self, *args: Any, **kwargs: Any) -> None:
        from engine.agent_core import persistence as ap
        from engine.agent_core.types import AgentRunRequest

        if args and isinstance(args[0], AgentRunRequest):
            req = args[0]
            run_id = kwargs["run_id"]
            session_id = kwargs["session_id"]
        else:
            run_id = args[0] if args else kwargs["run_id"]
            session_id = args[1] if len(args) > 1 else kwargs["session_id"]
            question = args[2] if len(args) > 2 else kwargs["question"]
            datasource_id = args[3] if len(args) > 3 else kwargs["datasource_id"]
            req = AgentRunRequest(
                datasource_id=datasource_id,
                question=question,
                session_id=session_id,
                parent_run_id=None,
                max_steps=50,
            )
        req = _request_with_session_id(req, session_id)
        ap.create_or_get_session(self.db, req, run_id)
        ap.start_run(self.db, req, run_id, session_id)

    def append_event(self, session_id: str, event: Any) -> None:
        from engine.agent_core import persistence as ap

        ap.record_runtime_event(self.db, session_id, event)

    def append_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        from engine.agent_core import persistence as ap

        ap.record_artifact(self.db, session_id, run_id, artifact, index)

    def create_approval(
        self,
        *,
        run_id: str,
        session_id: str,
        step_name: str,
        tool_name: str | None,
        risk_level: str,
        reason: str | None,
        policy_decision: dict[str, Any],
        requested_action: dict[str, Any] | None = None,
    ) -> Any | None:
        from engine.agent_core import persistence as ap

        return ap.create_approval(
            self.db,
            run_id=run_id,
            session_id=session_id,
            step_name=step_name,
            tool_name=tool_name,
            risk_level=risk_level,
            reason=reason,
            policy_decision=policy_decision,
            requested_action=requested_action,
        )

    def save_checkpoint(
        self,
        *,
        run_id: str,
        session_id: str,
        status: str,
        current_step_name: str | None,
        next_step_name: str | None,
        plan: Any | None,
        state: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        pending_steps: list[dict[str, Any]],
        artifacts: list[dict[str, Any]] | None = None,
        waiting_approval_id: str | None = None,
    ) -> Any | None:
        from engine.agent_core import persistence as ap

        checkpoint = ap.save_checkpoint(
            self.db,
            run_id=run_id,
            session_id=session_id,
            status=status,
            current_step_name=current_step_name,
            next_step_name=next_step_name,
            plan=plan,
            state=state,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            artifacts=artifacts,
        )
        if waiting_approval_id:
            ap.mark_run_waiting_approval(
                self.db,
                run_id=run_id,
                approval_id=waiting_approval_id,
                current_step_name=current_step_name or next_step_name or "approval_interrupt",
            )
        return checkpoint

    def complete_run(self, response: Any) -> None:
        from engine.agent_core import persistence as ap

        ap.complete_run(self.db, response)

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        from engine.agent_core import persistence as ap

        ap.fail_run(self.db, run_id, session_id, error, response)

    def cancel_run(self, run_id: str) -> None:
        from engine.agent_core import persistence as ap

        ap.cancel_run(self.db, run_id=run_id)

    def resolve_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        decision: str,
        note: str | None = None,
    ) -> Any | None:
        from engine.agent_core import persistence as ap

        return ap.resolve_approval(
            self.db,
            run_id=run_id,
            approval_id=approval_id,
            decision=decision,
            note=note,
        )

    def mark_run_resumed(self, run_id: str, current_step_name: str | None = "query_database") -> None:
        from engine.agent_core import persistence as ap

        ap.mark_run_resumed(self.db, run_id=run_id, current_step_name=current_step_name)

    def flush(self) -> None:
        self.db.flush()


class BufferedAgentEventStore(AgentEventStore):
    def __init__(self, target: AgentEventStore, *, flush_every: int = 20) -> None:
        self.target = target
        self.flush_every = max(1, flush_every)
        self._operations: list[Callable[[], None]] = []
        self._buffered_event_count = 0

    def start_run(self, *args: Any, **kwargs: Any) -> None:
        self._operations.append(lambda: self.target.start_run(*args, **kwargs))

    def append_event(self, session_id: str, event: Any) -> None:
        self._operations.append(lambda: self.target.append_event(session_id, event))
        self._buffered_event_count += 1
        self._flush_if_needed()

    def append_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        self._operations.append(lambda: self.target.append_artifact(session_id, run_id, artifact, index))
        self._buffered_event_count += 1
        self._flush_if_needed()

    def create_approval(
        self,
        *,
        run_id: str,
        session_id: str,
        step_name: str,
        tool_name: str | None,
        risk_level: str,
        reason: str | None,
        policy_decision: dict[str, Any],
        requested_action: dict[str, Any] | None = None,
    ) -> Any | None:
        result: list[Any | None] = []
        self._operations.append(
            lambda: result.append(
                self.target.create_approval(
                    run_id=run_id,
                    session_id=session_id,
                    step_name=step_name,
                    tool_name=tool_name,
                    risk_level=risk_level,
                    reason=reason,
                    policy_decision=policy_decision,
                    requested_action=requested_action,
                )
            )
        )
        self.flush()
        return result[0] if result else None

    def save_checkpoint(
        self,
        *,
        run_id: str,
        session_id: str,
        status: str,
        current_step_name: str | None,
        next_step_name: str | None,
        plan: Any | None,
        state: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        pending_steps: list[dict[str, Any]],
        artifacts: list[dict[str, Any]] | None = None,
        waiting_approval_id: str | None = None,
    ) -> Any | None:
        result: list[Any | None] = []
        self._operations.append(
            lambda: result.append(
                self.target.save_checkpoint(
                    run_id=run_id,
                    session_id=session_id,
                    status=status,
                    current_step_name=current_step_name,
                    next_step_name=next_step_name,
                    plan=plan,
                    state=state,
                    completed_steps=completed_steps,
                    pending_steps=pending_steps,
                    artifacts=artifacts,
                    waiting_approval_id=waiting_approval_id,
                )
            )
        )
        self.flush()
        return result[0] if result else None

    def complete_run(self, response: Any) -> None:
        self._operations.append(lambda: self.target.complete_run(response))
        self.flush()

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        self._operations.append(lambda: self.target.fail_run(run_id, session_id, error, response))
        self.flush()

    def cancel_run(self, run_id: str) -> None:
        self._operations.append(lambda: self.target.cancel_run(run_id))
        self.flush()

    def resolve_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        decision: str,
        note: str | None = None,
    ) -> Any | None:
        result: list[Any | None] = []
        self._operations.append(
            lambda: result.append(
                self.target.resolve_approval(
                    run_id=run_id,
                    approval_id=approval_id,
                    decision=decision,
                    note=note,
                )
            )
        )
        self.flush()
        return result[0] if result else None

    def mark_run_resumed(self, run_id: str, current_step_name: str | None = "query_database") -> None:
        self._operations.append(lambda: self.target.mark_run_resumed(run_id, current_step_name))
        self.flush()

    def flush(self) -> None:
        operations = self._operations
        self._operations = []
        self._buffered_event_count = 0
        try:
            for operation in operations:
                operation()
            self.target.flush()
        except Exception:
            self._operations = operations + self._operations
            raise

    def _flush_if_needed(self) -> None:
        if self._buffered_event_count >= self.flush_every:
            self.flush()


def create_agent_event_store(db: Session) -> AgentEventStore:
    mode = os.environ.get("AGENT_PERSISTENCE_MODE", "buffered").lower()
    if os.environ.get("DBFOX_TESTING") == "1":
        return SQLiteAgentEventStore(db)
    if mode in {"disabled", "noop", "none"}:
        return NoopAgentEventStore()
    if mode in {"session", "sqlite"}:
        return SQLiteAgentEventStore(db)
    return BufferedAgentEventStore(
        SQLiteAgentEventStore(db),
        flush_every=_buffered_flush_every(),
    )


def _buffered_flush_every() -> int:
    raw = os.environ.get("AGENT_PERSISTENCE_FLUSH_EVERY")
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return 20
