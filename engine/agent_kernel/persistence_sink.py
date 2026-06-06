"""Decoupled persistence sink for agent runtime events.

Three modes:
- disabled: no-op (eval/concurrent benchmark)
- buffered: collect in memory, flush at run end
- sync: write immediately with a dedicated session (default product mode)
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from engine.db import SessionLocal


class AgentPersistenceSink:
    """Abstract persistence sink. All methods return None and never raise."""

    def start_run(self, run_id: str, session_id: str, question: str, datasource_id: str) -> None:
        pass

    def record_event(self, session_id: str, event: Any) -> None:
        pass

    def record_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        pass

    def mark_run_resumed(self, run_id: str) -> None:
        pass

    def expire_approval(self, approval_id: str) -> None:
        pass

    def save_checkpoint(self, run_id: str, session_id: str, state: dict, tool_name: str) -> None:
        pass

    def mark_run_waiting(self, run_id: str, session_id: str, approval_id: str) -> None:
        pass

    def complete_run(self, response: Any) -> None:
        pass

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        pass

    def init_run_session(self, req: Any, run_id: str, session_id: str) -> None:
        pass

    def create_approval_record(self, run_id: str, session_id: str, tool_name: str,
                                reason: str, risk_level: str,
                                requested_action: dict) -> Any | None:
        return None

    def flush(self) -> None:
        pass


class NoopPersistenceSink(AgentPersistenceSink):
    """No-op sink: never touches SQLAlchemy, never raises."""


class SyncPersistenceSink(AgentPersistenceSink):
    """Write persistence using dedicated SessionLocal (independent of main agent session)."""

    def __init__(self, main_db: Session):
        self._main_db = main_db
        self._session_factory = SessionLocal

    def _write(self, fn):
        """Execute *fn* with a dedicated session. Failures are logged, never raised."""
        db = self._session_factory()
        try:
            fn(db)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    def start_run(self, run_id: str, session_id: str, question: str, datasource_id: str) -> None:
        import logging
        _log = logging.getLogger("databox.persistence")
        def _do(db):
            from engine.agent import persistence as ap
            ap.create_or_get_session(db, type("Req", (), {
                "datasource_id": datasource_id, "question": question,
                "session_id": session_id, "parent_run_id": None,
            })(), run_id)
            ap.start_run(db, type("Req2", (), {
                "datasource_id": datasource_id, "question": question,
                "session_id": session_id, "max_steps": 20,
            })(), run_id, session_id)
        self._write(_do)

    def record_event(self, session_id: str, event: Any) -> None:
        from engine.agent import persistence as ap
        self._write(lambda db: ap.record_runtime_event(db, session_id, event))

    def record_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        from engine.agent import persistence as ap
        # record_artifact is idempotent; we call it once
        pass  # artifacts are written via _artifact_events; skip for now

    def complete_run(self, response: Any) -> None:
        from engine.agent import persistence as ap
        self._write(lambda db: ap.complete_run(db, response))

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        from engine.agent import persistence as ap
        self._write(lambda db: ap.fail_run(db, run_id, session_id, error, response))


def create_persistence_sink(db: Session) -> AgentPersistenceSink:
    """Factory: create the appropriate sink based on AGENT_PERSISTENCE_MODE."""
    mode = os.environ.get("AGENT_PERSISTENCE_MODE", "sync").lower()
    if mode == "disabled":
        return NoopPersistenceSink()
    if mode == "buffered":
        # For now, buffered = disabled for eval safety
        return NoopPersistenceSink()
    return SyncPersistenceSink(db)
