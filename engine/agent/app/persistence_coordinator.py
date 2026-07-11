from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator
from engine.agent_core.events import EventEmitter
from engine.agent_core.types import AgentRunRequest, AgentRunResponse, AgentRuntimeEvent
from engine.app.safe_errors import FixedErrorCode, SafeLogOperation, log_unexpected_exception

logger = logging.getLogger("dbfox.dbfox_agent.persistence_coordinator")


class AgentPersistenceCoordinator:
    """Coordinate runtime event, artifact, checkpoint, and final response persistence."""

    def __init__(
        self,
        db: Session,
        event_store: Any,
        memory_projection: AgentMemoryProjectionCoordinator,
        *,
        enabled: bool,
    ):
        self.db = db
        self.event_store = event_store
        self.memory_projection = memory_projection
        self.enabled = enabled

    def start_run(self, req: AgentRunRequest, *, run_id: str, session_id: str) -> None:
        if not self.enabled:
            return
        try:
            self.event_store.start_run(req, run_id=run_id, session_id=session_id)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_PERSISTENCE_START,
                exc=exc,
                level="warning",
            )
            self.rollback_quietly()

    def build_emitter(self, run_id: str, session_id: str, start_sequence: int) -> EventEmitter:
        def save(event: AgentRuntimeEvent) -> None:
            if self.enabled:
                try:
                    self.event_store.append_event(session_id, event)
                except Exception as exc:
                    log_unexpected_exception(
                        logger,
                        operation=SafeLogOperation.AGENT_PERSISTENCE_EVENT,
                        exc=exc,
                        level="warning",
                    )
                    self.rollback_quietly()

        return EventEmitter(run_id, save, start_sequence=start_sequence)

    def persist_artifact_event(
        self,
        session_id: str,
        event: AgentRuntimeEvent,
        *,
        index: int,
    ) -> None:
        if (
            not self.enabled
            or event.type != "agent.artifact.created"
            or event.artifact is None
        ):
            return
        try:
            self.event_store.append_artifact(session_id, event.run_id, event.artifact, index)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_PERSISTENCE_ARTIFACT,
                exc=exc,
                level="warning",
            )

    def flush(self, run_id: str, purpose: str) -> None:
        if not self.enabled:
            return
        try:
            self.event_store.flush()
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_PERSISTENCE_FLUSH,
                exc=exc,
                level="warning",
            )
            self.rollback_quietly()

    def save_approval_checkpoint(
        self,
        *,
        run_id: str,
        session_id: str,
        draft: Any,
    ) -> Any:
        if not self.enabled:
            return None
        try:
            checkpoint = self.event_store.save_checkpoint(
                run_id=run_id,
                session_id=session_id,
                status=draft.status,
                current_step_name=draft.current_step_name,
                next_step_name=draft.next_step_name,
                plan=draft.plan,
                state=draft.state,
                completed_steps=draft.completed_steps,
                pending_steps=draft.pending_steps,
                artifacts=draft.artifacts,
                waiting_approval_id=draft.waiting_approval_id,
            )
            self.db.commit()
            return checkpoint
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_PERSISTENCE_APPROVAL_CHECKPOINT,
                exc=exc,
                level="warning",
            )
            self.rollback_quietly()
            return None

    def cancel_run(self, run_id: str) -> None:
        try:
            self.event_store.cancel_run(run_id)
            self.db.commit()
        except Exception:
            self.rollback_quietly()

    def mark_run_resumed(self, run_id: str) -> None:
        self.event_store.mark_run_resumed(run_id)

    def finalize(
        self,
        emit: Any,
        response: AgentRunResponse,
        *,
        final_state: dict[str, Any] | None = None,
        datasource_id: str | None = None,
    ) -> AgentRuntimeEvent:
        if response.success:
            event = emit("agent.run.completed", response=response)
        else:
            event = emit("agent.run.failed", response=response, error=response.error)

        if self.enabled:
            try:
                if response.success:
                    self.event_store.complete_run(response)
                    if final_state is not None and datasource_id:
                        self.memory_projection.save_run_projection(
                            response,
                            final_state=final_state,
                            datasource_id=datasource_id,
                        )
                else:
                    self.event_store.fail_run(
                        response.run_id, response.session_id,
                        FixedErrorCode.AGENT_RUNTIME_ERROR,
                        response,
                    )
                self.db.commit()
            except Exception as exc:
                log_unexpected_exception(
                    logger,
                    operation=SafeLogOperation.AGENT_PERSISTENCE_FINAL_RESPONSE,
                    exc=exc,
                    level="warning",
                )
                self.rollback_quietly()

        return event

    def rollback_quietly(self) -> None:
        try:
            self.db.rollback()
        except Exception:
            pass
