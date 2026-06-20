"""Decoupled persistence sink for agent runtime events.

Three modes:
- disabled: no-op (eval/concurrent benchmark)
- buffered: collect in memory, flush at run end
- sync: write immediately with a dedicated session (default product mode)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from engine.db import SessionLocal

logger = logging.getLogger("dbfox.persistence_sink")


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

    def save_checkpoint(self, run_id: str, session_id: str, state: dict[str, Any], tool_name: str) -> None:
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
                                requested_action: dict[str, Any]) -> Any | None:
        return None

    def flush(self) -> None:
        pass


class NoopPersistenceSink(AgentPersistenceSink):
    """No-op sink: never touches SQLAlchemy, never raises."""


class SessionPersistenceSink(AgentPersistenceSink):
    """Write persistence through the caller-owned SQLAlchemy session."""

    def __init__(self, db: Session):
        self._db = db

    def init_run_session(self, req: Any, run_id: str, session_id: str) -> None:
        from engine.agent_core import persistence as ap
        ap.create_or_get_session(self._db, req, run_id)
        ap.start_run(self._db, req, run_id, session_id)

    def record_event(self, session_id: str, event: Any) -> None:
        from engine.agent_core import persistence as ap
        ap.record_runtime_event(self._db, session_id, event)

    def complete_run(self, response: Any) -> None:
        from engine.agent_core import persistence as ap
        ap.complete_run(self._db, response)

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        from engine.agent_core import persistence as ap
        ap.fail_run(self._db, run_id, session_id, error, response)


class SyncPersistenceSink(AgentPersistenceSink):
    """Write persistence using dedicated SessionLocal (independent of main agent session)."""

    def __init__(self, main_db: Session):
        self._main_db = main_db
        self._session_factory = SessionLocal

    def _write(self, fn: Callable[[Session], None], max_retries: int = 3) -> None:
        """Execute *fn* with a dedicated session. Retries on lock with backoff."""
        import time as _time
        last_error = None
        for attempt in range(max_retries):
            db = self._session_factory()
            try:
                fn(db)
                db.commit()
                return
            except Exception as exc:
                last_error = exc
                try:
                    db.rollback()
                except Exception:
                    pass
                # SQLite lock is transient — retry after backoff
                if attempt < max_retries - 1:
                    _time.sleep(0.05 * (attempt + 1))
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        logger.error(
            "Persistence write failed after %d retries: %s",
            max_retries, last_error,
        )

    def start_run(self, run_id: str, session_id: str, question: str, datasource_id: str) -> None:
        import logging
        _log = logging.getLogger("dbfox.persistence")
        def _do(db: Session) -> None:
            from engine.agent_core import persistence as ap
            from engine.agent_core.types import AgentRunRequest
            req = AgentRunRequest(
                datasource_id=datasource_id,
                question=question,
                session_id=session_id,
                parent_run_id=None,
                max_steps=50,
            )
            ap.create_or_get_session(db, req, run_id)
            ap.start_run(db, req, run_id, session_id)
        self._write(_do)

    def init_run_session(self, req: Any, run_id: str, session_id: str) -> None:
        def _do(db: Session) -> None:
            from engine.agent_core import persistence as ap
            ap.create_or_get_session(db, req, run_id)
            ap.start_run(db, req, run_id, session_id)
        self._write(_do)

    def record_event(self, session_id: str, event: Any) -> None:
        from engine.agent_core import persistence as ap
        self._write(lambda db: ap.record_runtime_event(db, session_id, event))

    def record_artifact(self, session_id: str, run_id: str, artifact: Any, index: int) -> None:
        from engine.agent_core import persistence as ap
        self._write(lambda db: ap.record_artifact(db, session_id, run_id, artifact, index))

    def complete_run(self, response: Any) -> None:
        from engine.agent_core import persistence as ap
        self._write(lambda db: ap.complete_run(db, response))

    def fail_run(self, run_id: str, session_id: str, error: str, response: Any) -> None:
        from engine.agent_core import persistence as ap
        self._write(lambda db: ap.fail_run(db, run_id, session_id, error, response))


def create_persistence_sink(db: Session) -> AgentPersistenceSink:
    """Factory: create the appropriate sink based on AGENT_PERSISTENCE_MODE."""
    mode = os.environ.get("AGENT_PERSISTENCE_MODE", "sync").lower()
    if os.environ.get("DBFOX_TESTING") == "1":
        return SessionPersistenceSink(db)
    if mode == "disabled":
        return NoopPersistenceSink()
    if mode == "buffered":
        # For now, buffered = disabled for eval safety
        return NoopPersistenceSink()
    return SyncPersistenceSink(db)
