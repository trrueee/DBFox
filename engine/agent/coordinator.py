"""Session-scoped scheduling, recovery and database lease fencing."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, RLock, Thread
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.loop import RunLoop
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunStatus
from engine.agent.session import SessionInputStatus, SessionLease
from engine.models import AgentRun, AgentSessionInput


logger = logging.getLogger("dbfox.agent.coordinator")


class SessionCoordinator:
    """Serializes one Session while allowing independent Sessions in parallel."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        run_loop: RunLoop,
        max_workers: int = 4,
        lease_ttl_seconds: int = 120,
    ) -> None:
        self.session_factory = session_factory
        self.run_loop = run_loop
        self.lease_ttl_seconds = lease_ttl_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dbfox-agent")
        self._active: dict[str, Future[None]] = {}
        self._lock = RLock()
        self._stopped = Event()

    @property
    def available(self) -> bool:
        return not self._stopped.is_set()

    def start(self) -> None:
        if self._stopped.is_set():
            raise RuntimeError("SessionCoordinator has stopped")
        for session_id in self._recoverable_sessions():
            self.wake(session_id)

    def wake(self, session_id: str) -> None:
        if self._stopped.is_set():
            raise RuntimeError("SessionCoordinator has stopped")
        with self._lock:
            current = self._active.get(session_id)
            if current is not None and not current.done():
                return
            future = self._executor.submit(self._drain_session, session_id)
            self._active[session_id] = future
            future.add_done_callback(lambda _: self._finished(session_id))

    def stop(self, *, wait: bool = True) -> None:
        self._stopped.set()
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _drain_session(self, session_id: str) -> None:
        owner = f"worker:{uuid4().hex}"
        while not self._stopped.is_set():
            lease, run_id = self._claim_work(session_id, owner)
            if lease is None or run_id is None:
                return
            heartbeat_stop = Event()
            heartbeat = Thread(
                target=self._heartbeat,
                args=(lease, heartbeat_stop),
                name=f"dbfox-agent-heartbeat-{session_id[:12]}",
                daemon=True,
            )
            heartbeat.start()
            try:
                self.run_loop.execute(lease=lease, run_id=run_id)
            except Exception:
                logger.exception("Agent RunLoop failed run_id=%s", run_id)
                try:
                    with self.session_factory() as db:
                        RunRepository(db).fail(
                            lease=lease, run_id=run_id,
                            error_code="AGENT_RUNTIME_ERROR",
                            message="分析未能完成，请重试。",
                        )
                        db.commit()
                except Exception:
                    logger.exception("Agent failure terminalization failed run_id=%s", run_id)
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=2)

    def _claim_work(self, session_id: str, owner: str) -> tuple[SessionLease | None, str | None]:
        with self.session_factory() as db:
            sessions = SessionRepository(db)
            lease = sessions.claim(
                session_id=session_id, owner=owner, ttl_seconds=self.lease_ttl_seconds
            )
            if lease is None:
                db.rollback()
                return None, None
            waiting = db.execute(
                select(AgentRun).where(
                    AgentRun.session_id == session_id,
                    AgentRun.status.in_([
                        RunStatus.WAITING_APPROVAL.value,
                        RunStatus.WAITING_INPUT.value,
                    ]),
                ).order_by(AgentRun.session_sequence)
            ).scalars().first()
            if waiting is not None:
                sessions.release(lease=lease)
                db.commit()
                return None, None
            run = db.execute(
                select(AgentRun).where(
                    AgentRun.session_id == session_id,
                    AgentRun.status.in_([RunStatus.RUNNING.value, RunStatus.CANCELLING.value]),
                ).order_by(AgentRun.session_sequence)
            ).scalars().first()
            run_id: str | None
            if run is not None:
                sessions.bind_run(lease=lease, run_id=str(run.id))
                run_id = str(run.id)
            else:
                run_id = sessions.promote_next_input(lease=lease)
            if run_id is None:
                sessions.release(lease=lease)
            db.commit()
            return (lease, run_id) if run_id else (None, None)

    def _heartbeat(self, lease: SessionLease, stop: Event) -> None:
        interval = max(1.0, self.lease_ttl_seconds / 3)
        while not stop.wait(interval):
            try:
                with self.session_factory() as db:
                    SessionRepository(db).heartbeat(
                        lease=lease, ttl_seconds=self.lease_ttl_seconds
                    )
                    db.commit()
            except Exception:
                return

    def _recoverable_sessions(self) -> list[str]:
        with self.session_factory() as db:
            input_sessions = db.execute(
                select(AgentSessionInput.session_id).where(
                    AgentSessionInput.status == SessionInputStatus.ADMITTED.value
                ).distinct()
            ).scalars()
            run_sessions = db.execute(
                select(AgentRun.session_id).where(
                    AgentRun.status.in_([RunStatus.RUNNING.value, RunStatus.CANCELLING.value])
                ).distinct()
            ).scalars()
            return sorted({str(value) for value in [*input_sessions, *run_sessions]})

    def _has_work(self, session_id: str) -> bool:
        with self.session_factory() as db:
            return db.execute(
                select(AgentSessionInput.id).where(
                    AgentSessionInput.session_id == session_id,
                    AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
                ).limit(1)
            ).scalar_one_or_none() is not None

    def _finished(self, session_id: str) -> None:
        with self._lock:
            self._active.pop(session_id, None)
        if not self._stopped.is_set() and self._has_work(session_id):
            self.wake(session_id)
