"""Session-scoped scheduling, recovery and database lease fencing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event, RLock, Thread, current_thread
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.loop import RunLoop
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunStatus, SessionLeaseConflict
from engine.agent.session import SessionInputStatus, SessionLease
from engine.models import (
    AgentApproval,
    AgentQuestionRequest,
    AgentRun,
    AgentSessionInput,
)


logger = logging.getLogger("dbfox.agent.coordinator")


@dataclass(frozen=True)
class _ActiveSession:
    future: Future[None]
    interrupt: Event


class SessionCoordinator:
    """Serializes one Session while allowing independent Sessions in parallel."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        run_loop: RunLoop,
        max_workers: int = 4,
        max_scheduled_sessions: int | None = None,
        lease_ttl_seconds: int = 120,
    ) -> None:
        self.session_factory = session_factory
        self.run_loop = run_loop
        self.lease_ttl_seconds = lease_ttl_seconds
        self.max_scheduled_sessions = (
            max_workers * 2
            if max_scheduled_sessions is None
            else max_scheduled_sessions
        )
        if self.max_scheduled_sessions < max_workers:
            raise ValueError("max_scheduled_sessions must be at least max_workers")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dbfox-agent")
        self._active: dict[str, _ActiveSession] = {}
        self._lock = RLock()
        self._stopped = Event()
        self._maintenance: Thread | None = None

    @property
    def available(self) -> bool:
        return not self._stopped.is_set()

    def start(self) -> None:
        if self._stopped.is_set():
            raise RuntimeError("SessionCoordinator has stopped")
        for session_id in self._recoverable_sessions():
            self.wake(session_id)
        with self._lock:
            if self._maintenance is None or not self._maintenance.is_alive():
                self._maintenance = Thread(
                    target=self._maintenance_loop,
                    name="dbfox-agent-maintenance",
                    daemon=True,
                )
                self._maintenance.start()

    def wake(self, session_id: str) -> bool:
        """Schedule a bounded in-memory wake hint; durable work stays in the database."""
        if self._stopped.is_set():
            raise RuntimeError("SessionCoordinator has stopped")
        with self._lock:
            current = self._active.get(session_id)
            if current is not None and not current.future.done():
                return True
            if len(self._active) >= self.max_scheduled_sessions:
                return False
            interrupt = Event()
            future = self._executor.submit(self._drain_session, session_id, interrupt)
            self._active[session_id] = _ActiveSession(future=future, interrupt=interrupt)
            future.add_done_callback(partial(self._finished, session_id))
            return True

    def stop(self, *, wait: bool = True) -> None:
        self._stopped.set()
        with self._lock:
            for active in self._active.values():
                active.interrupt.set()
        self._executor.shutdown(wait=wait, cancel_futures=False)
        close_run_loop = getattr(self.run_loop, "close", None)
        if callable(close_run_loop):
            close_run_loop()
        maintenance = self._maintenance
        if maintenance is not None and maintenance is not current_thread():
            maintenance.join(timeout=2)

    def _drain_session(self, session_id: str, interrupt: Event) -> None:
        owner = f"worker:{uuid4().hex}"
        while not self._stopped.is_set() and not interrupt.is_set():
            try:
                lease, run_id = self._claim_work(session_id, owner)
            except Exception:
                logger.exception("Agent work claim failed session_id=%s", session_id)
                if self._stopped.wait(1.0):
                    return
                continue
            if lease is None or run_id is None:
                return
            heartbeat_stop = Event()
            heartbeat = Thread(
                target=self._heartbeat,
                args=(lease, heartbeat_stop, interrupt),
                name=f"dbfox-agent-heartbeat-{session_id[:12]}",
                daemon=True,
            )
            heartbeat.start()
            try:
                self.run_loop.execute(lease=lease, run_id=run_id, lease_lost=interrupt)
            except Exception:
                logger.exception("Agent RunLoop failed run_id=%s", run_id)
                try:
                    self.run_loop.terminalizer.fail(
                        lease,
                        run_id,
                        "AGENT_RUNTIME_ERROR",
                        "分析未能完成，请重试。",
                    )
                except Exception:
                    logger.exception("Agent failure terminalization failed run_id=%s", run_id)
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=2)
            self._delete_if_ready(session_id)

    def _claim_work(self, session_id: str, owner: str) -> tuple[SessionLease | None, str | None]:
        with self.session_factory() as db:
            sessions = SessionRepository(db)
            lease = sessions.claim(
                session_id=session_id, owner=owner, ttl_seconds=self.lease_ttl_seconds
            )
            if lease is None:
                db.rollback()
                return None, None
            ApprovalRepository(db).expire_pending(lease=lease)
            QuestionRepository(db).expire_pending(lease=lease)
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

    def _delete_if_ready(self, session_id: str) -> bool:
        """Physically delete a soft-deleted Session after every Run is terminal."""
        with self.session_factory() as db:
            from engine.models import AgentSession

            aggregate = db.get(AgentSession, session_id)
            if aggregate is None or aggregate.deleted_at is None:
                return False
            active = db.execute(
                select(AgentRun.id).where(
                    AgentRun.session_id == session_id,
                    AgentRun.status.not_in(
                        [RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value]
                    ),
                ).limit(1)
            ).scalar_one_or_none()
            if active is not None:
                return False
            db.delete(aggregate)
            db.commit()
            return True

    def _heartbeat(self, lease: SessionLease, stop: Event, lease_lost: Event | None = None) -> None:
        interval = max(1.0, self.lease_ttl_seconds / 3)
        delay = interval
        failures = 0
        while not stop.wait(delay):
            try:
                with self.session_factory() as db:
                    SessionRepository(db).heartbeat(
                        lease=lease, ttl_seconds=self.lease_ttl_seconds
                    )
                    db.commit()
                failures = 0
                delay = interval
            except SessionLeaseConflict:
                if lease_lost is not None:
                    lease_lost.set()
                logger.warning(
                    "Agent Session lease was lost session_id=%s owner=%s token=%s",
                    lease.session_id,
                    lease.owner,
                    lease.token,
                )
                return
            except Exception:
                failures += 1
                delay = min(interval, float(2 ** min(failures - 1, 5)))
                logger.exception(
                    "Agent Session heartbeat failed; retrying session_id=%s attempt=%s",
                    lease.session_id,
                    failures,
                )

    def _recoverable_sessions(self) -> list[str]:
        with self.session_factory() as db:
            now = datetime.now(UTC)
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
            approval_sessions = db.execute(
                select(AgentApproval.session_id).where(
                    AgentApproval.status == "pending",
                    AgentApproval.expires_at.is_not(None),
                    AgentApproval.expires_at <= now,
                ).distinct()
            ).scalars()
            question_sessions = db.execute(
                select(AgentQuestionRequest.session_id).where(
                    AgentQuestionRequest.status == "pending",
                    AgentQuestionRequest.expires_at.is_not(None),
                    AgentQuestionRequest.expires_at <= now,
                ).distinct()
            ).scalars()
            return sorted({
                str(value)
                for value in [
                    *input_sessions,
                    *run_sessions,
                    *approval_sessions,
                    *question_sessions,
                ]
            })

    def _maintenance_loop(self) -> None:
        while not self._stopped.wait(5.0):
            try:
                recoverable = self._recoverable_sessions()
            except Exception:
                logger.exception("Agent maintenance scan failed")
                continue
            for session_id in recoverable:
                if self._stopped.is_set():
                    return
                try:
                    self.wake(session_id)
                except RuntimeError:
                    if self._stopped.is_set():
                        return
                    raise

    def _has_work(self, session_id: str) -> bool:
        with self.session_factory() as db:
            return db.execute(
                select(AgentSessionInput.id).where(
                    AgentSessionInput.session_id == session_id,
                    AgentSessionInput.status == SessionInputStatus.ADMITTED.value,
                ).limit(1)
            ).scalar_one_or_none() is not None

    def _finished(self, session_id: str, completed: Future[None]) -> None:
        with self._lock:
            current = self._active.get(session_id)
            if current is None or current.future is not completed:
                return
            self._active.pop(session_id)
        if not self._stopped.is_set() and self._has_work(session_id):
            self.wake(session_id)
