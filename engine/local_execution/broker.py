"""Durable Job facts and ownership of live local processes inside one Sidecar."""

from __future__ import annotations

import codecs
import logging
import os
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from engine.agent.run import RunStatus, TERMINAL_RUN_STATUSES
from engine.diagnostics.logs import redact_sensitive_text
from engine.json_codec import canonical_dumps, load_object
from engine.local_execution.command import ExecutionError, PreparedCommand, prepare
from engine.local_execution.contracts import (
    ACTIVE_STATES, LOG_CHUNK_BYTES, ExecutionScope, JobPage, JobView, LogLine, StartInput, WorkspaceDirectory,
)
from engine.local_execution.records import LocalExecutionJob, LocalExecutionLog
from engine.models import AgentRun, AgentSession
from engine.resource import ResourceScopeRef

if TYPE_CHECKING:
    from engine.local_execution.windows import WindowsProcess

logger = logging.getLogger(__name__)
_JOB_LOG_BYTES = 8 * 1024 * 1024
_TOTAL_LOG_BYTES = 256 * 1024 * 1024
_LOG_TTL_MS = 7 * 24 * 60 * 60 * 1000
_MAX_LIVE_JOBS = 8
_MAX_RUN_JOBS = 4
_STREAMS = ("stdout", "stderr")
_DRAIN_SECONDS = 3


def supported() -> bool:
    return sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"} and (
        sys.getwindowsversion().build >= 22000
    )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(slots=True)
class _LiveJob:
    id: str
    run_id: str
    scope: ExecutionScope
    process: WindowsProcess
    background: bool
    deadline: float
    wake: Event = field(default_factory=Event)
    done: Event = field(default_factory=Event)
    stdin_lock: Lock = field(default_factory=Lock)
    stop_reason: str | None = None
    thread: Thread | None = None

    def request_stop(self, reason: str) -> None:
        self.stop_reason = self.stop_reason or reason
        self.wake.set()


class LocalExecutionBroker:
    def __init__(
        self, session_factory: Callable[[], Session],
        resolve_workspace: Callable[[ResourceScopeRef], WorkspaceDirectory],
    ) -> None:
        if not supported():
            raise RuntimeError("Managed local execution requires Windows 11 x64")
        self._sessions = session_factory
        self.resolve_workspace = resolve_workspace
        self.generation = uuid4().hex
        self._lock = Lock()
        self._jobs: dict[str, _LiveJob] = {}
        self._closing = False
        self._next_sweep = 0.0
        with self._sessions() as db, db.begin():
            # A new Sidecar never tries to recover or re-run a command by PID.
            db.execute(update(LocalExecutionJob).where(LocalExecutionJob.state.in_(ACTIVE_STATES)).values(
                state="interrupted", reason="sidecar_restarted", active_processes=None,
                stdin_open=False, output_finalized=False, finished_at=_now_ms(),
            ))
            self._sweep(db)

    def start(
        self, *, scope: ExecutionScope, run_id: str, invocation_id: str, approval_id: str,
        input: StartInput, resource: WorkspaceDirectory, is_approved: Callable[[PreparedCommand], bool],
        is_cancelled: Callable[[], bool],
    ) -> JobView:
        from engine.local_execution.windows import WindowsProcess

        with self._lock:
            if self._closing or is_cancelled():
                raise ExecutionError("The Run or Sidecar is stopping.")
            with self._sessions() as db:
                existing = db.scalar(select(LocalExecutionJob).where(LocalExecutionJob.invocation_id == invocation_id))
                if existing is not None:
                    self._require_job(db, existing.id, scope)
                    if existing.approval_id != approval_id or existing.run_id != run_id:
                        raise ExecutionError("The existing Job belongs to a different invocation authority.")
                    return self._view(existing)
            if len(self._jobs) >= _MAX_LIVE_JOBS or sum(
                live.run_id == run_id for live in self._jobs.values()
            ) >= _MAX_RUN_JOBS:
                raise ExecutionError("The live Job limit has been reached. Stop an existing Job first.")
            if self._owner_reason(scope, run_id, background=False):
                raise ExecutionError("The originating Run is no longer active.")

            command = prepare(input, resource.command_directory(input.cwd))
            if not is_approved(command):
                raise ExecutionError("The approved command or its authority changed before launch.")
            job = LocalExecutionJob(
                id=f"job_{uuid4().hex}", invocation_id=invocation_id, approval_id=approval_id,
                run_id=run_id, session_id=scope.session_id, workspace_id=scope.workspace.id,
                workspace_generation=scope.workspace.version, engine_generation=self.generation,
                command_json=canonical_dumps({**command.display(), "argv": input.argv, "shell_script": input.shell_script}),
                state="starting", stdin_open=False, output_finalized=False, first_cursor=1, last_cursor=0,
                total_bytes=0, retained_bytes=0, created_at=_now_ms(),
            )
            with self._sessions() as db:
                db.add(job)
                db.commit()
                db.refresh(job)
            try:
                with resource.execution_directory(input.cwd) as directory:
                    command = prepare(input, directory)
                    if not is_approved(command) or is_cancelled():
                        raise ExecutionError("The approved command or its authority changed before launch.")
                    process = WindowsProcess.launch(
                        command.program, command.command_line, directory, command.environment,
                        interactive=input.interactive,
                    )
            except (OSError, ValueError) as exc:
                code = getattr(exc, "winerror", None)
                reason = f"win32_start_{code}" if isinstance(code, int) else "authority_or_launch_failed"
                self._finish(job.id, "start_failed", reason, None, None, False)
                raise ExecutionError(f"The approved process could not start ({reason}).") from exc

            live = _LiveJob(
                job.id, run_id, scope, process, input.lifetime == "background",
                time.monotonic() + input.timeout_seconds,
            )
            try:
                with self._sessions() as db, db.begin():
                    db.execute(update(LocalExecutionJob).where(LocalExecutionJob.id == job.id).values(
                        state="running", stdin_open=input.interactive,
                    ))
                job.state = "running"
                job.stdin_open = input.interactive
                live.thread = Thread(target=self._monitor, args=(live,), name=job.id, daemon=True)
                self._jobs[job.id] = live
                live.thread.start()
            except Exception:
                self._jobs.pop(job.id, None)
                process.close()
                self._finish(job.id, "unknown", "supervision_failed", None, None, False)
                raise
            return self._view(job)

    @staticmethod
    def _view(job: LocalExecutionJob) -> JobView:
        command = load_object(job.command_json)
        return JobView.model_validate({
            "id": job.id, "run_id": job.run_id, "state": job.state, "reason": job.reason,
            **{key: command[key] for key in (
                "executable", "argv", "shell_script", "cwd", "lifetime", "interactive", "timeout_seconds",
            )},
            "stdin_open": job.stdin_open, "root_exit_code": job.root_exit_code,
            "active_processes": job.active_processes, "output_finalized": job.output_finalized,
            "first_cursor": job.first_cursor, "last_cursor": job.last_cursor, "retained_bytes": job.retained_bytes,
            "duration_ms": max(0, (job.finished_at or _now_ms()) - job.created_at),
        })

    def _require_job(self, db: Session, job_id: str, scope: ExecutionScope) -> LocalExecutionJob:
        job = db.get(LocalExecutionJob, job_id)
        if job is None or (
            job.session_id, job.workspace_id, job.workspace_generation
        ) != (scope.session_id, scope.workspace.id, scope.workspace.version):
            raise ExecutionError("The execution Job is unavailable in this conversation and Workspace binding.")
        return job

    def list_jobs(self, scope: ExecutionScope) -> list[JobView]:
        self.resolve_workspace(scope.workspace)
        with self._sessions() as db:
            rows = db.scalars(select(LocalExecutionJob).where(
                LocalExecutionJob.session_id == scope.session_id,
                LocalExecutionJob.workspace_id == scope.workspace.id,
                LocalExecutionJob.workspace_generation == scope.workspace.version,
            ).order_by(LocalExecutionJob.created_at.desc()).limit(40))
            return [self._view(row) for row in rows]

    def page(self, scope: ExecutionScope, job_id: str, after: int, limit: int, *, tail: bool = False) -> JobPage:
        self.resolve_workspace(scope.workspace)
        with self._lock, self._sessions() as db, db.begin():
            self._sweep(db)
            job = self._require_job(db, job_id, scope)
            if after > job.last_cursor:
                raise ExecutionError("The log cursor is beyond the last recorded output.")
            floor = job.first_cursor - 1
            cursor = max(job.last_cursor - limit if tail else after, floor)
            rows = list(db.scalars(select(LocalExecutionLog).where(
                LocalExecutionLog.job_id == job_id, LocalExecutionLog.cursor > cursor,
            ).order_by(LocalExecutionLog.cursor).limit(limit)))
            decoders = {}
            chunks = []
            for row in rows:
                stream = row.stream
                if stream not in decoders:
                    decoder = codecs.getincrementaldecoder("utf-8")("replace")
                    if cursor > floor:
                        prior = db.scalar(select(LocalExecutionLog.data).where(
                            LocalExecutionLog.job_id == job_id, LocalExecutionLog.stream == stream,
                            LocalExecutionLog.cursor <= cursor,
                        ).order_by(LocalExecutionLog.cursor.desc()).limit(1))
                        if prior:
                            decoder.decode(prior)
                    decoders[stream] = decoder
                chunks.append(LogLine(
                    cursor=row.cursor, stream=stream,
                    text=redact_sensitive_text(decoders[stream].decode(row.data)),
                ))
            next_cursor = rows[-1].cursor if rows else cursor
            return JobPage(
                job=self._view(job), chunks=chunks, next_cursor=next_cursor,
                cursor_expired=after < floor, has_more=next_cursor < job.last_cursor,
            )

    def get(self, scope: ExecutionScope, job_id: str) -> JobView:
        self.resolve_workspace(scope.workspace)
        with self._sessions() as db:
            return self._view(self._require_job(db, job_id, scope))

    def stop(self, scope: ExecutionScope, job_id: str) -> JobView:
        job = self.get(scope, job_id)
        with self._lock:
            live = self._jobs.get(job_id)
            if live is not None:
                live.request_stop("stop_requested")
        return job

    def cancel_invocation(self, invocation_id: str) -> None:
        with self._sessions() as db:
            job_id = db.scalar(select(LocalExecutionJob.id).where(LocalExecutionJob.invocation_id == invocation_id))
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].request_stop("invocation_cancelled")

    def write(self, scope: ExecutionScope, job_id: str, text: str, *, close: bool) -> int:
        job = self.get(scope, job_id)
        if not job.stdin_open:
            raise ExecutionError("The Job has no open stdin pipe.")
        payload = text.encode("utf-8")
        if len(payload) > LOG_CHUNK_BYTES:
            raise ExecutionError("One stdin write may contain at most 4096 UTF-8 bytes.")
        with self._lock:
            live = self._jobs.get(job_id)
            if live is None or live.stop_reason or not live.stdin_lock.acquire(blocking=False):
                raise ExecutionError("The Job is stopping or already handling a stdin write.")
        completed = Event()
        result: list[int] = []

        def write_pipe() -> None:
            try:
                fd = live.process.duplicate_stdin()
                try:
                    count = os.write(fd, payload) if payload else 0
                finally:
                    os.close(fd)
                if close:
                    live.process.close_stdin()
                result.append(count)
            except OSError:
                pass
            finally:
                live.stdin_lock.release()
                completed.set()
                live.wake.set()

        try:
            Thread(target=write_pipe, name=f"{job_id}-stdin", daemon=True).start()
        except Exception:
            live.stdin_lock.release()
            raise
        if not completed.wait(2):
            live.request_stop("stdin_timeout")
            raise ExecutionError("The process did not accept stdin in time. Stop was requested and input may be partial.")
        if not result or result[0] != len(payload):
            raise ExecutionError("The process closed stdin or accepted only part of the write. Inspect before retrying.")
        return result[0]

    def wait(
        self, scope: ExecutionScope, job_id: str, cancelled: Callable[[], bool],
    ) -> JobView:
        with self._lock:
            live = self._jobs.get(job_id)
        if live is not None:
            while not live.done.wait(0.15):
                if cancelled():
                    live.request_stop("invocation_cancelled")
                    raise ExecutionError("The command invocation was cancelled.")
        return self.get(scope, job_id)

    def close(self) -> None:
        with self._lock:
            self._closing = True
            live_jobs = tuple(self._jobs.values())
            for live in live_jobs:
                live.request_stop("sidecar_shutdown")
        deadline = time.monotonic() + 5
        for live in live_jobs:
            if not live.done.wait(max(0, deadline - time.monotonic())):
                live.process.close_job()

    def _owner_reason(self, scope: ExecutionScope, run_id: str, *, background: bool) -> str | None:
        with self._sessions() as db:
            row = db.execute(select(
                AgentRun.status, AgentRun.cancel_requested, AgentSession.deleted_at,
            ).join(AgentSession, AgentRun.session_id == AgentSession.id).where(
                AgentRun.id == run_id, AgentSession.id == scope.session_id,
                AgentSession.project_id == scope.workspace.id,
            )).one_or_none()
        if row is None or row.deleted_at is not None:
            return "conversation_removed"
        if row.cancel_requested or row.status == RunStatus.CANCELLING:
            return "run_cancelled"
        if row.status in TERMINAL_RUN_STATUSES and (not background or row.status != RunStatus.COMPLETED):
            return f"run_{row.status}"
        return None

    def _monitor(self, live: _LiveJob) -> None:
        process = live.process
        root_code = None
        active = None
        open_streams = set(_STREAMS)
        stop_reason = None
        next_owner_check = 0.0
        drain_deadline = None
        stop_deadline = None
        previous_facts = None
        try:
            while True:
                now = time.monotonic()
                if now >= next_owner_check and not stop_reason:
                    next_owner_check = now + 0.5
                    reason = self._owner_reason(live.scope, live.run_id, background=live.background)
                    try:
                        self.resolve_workspace(live.scope.workspace)
                    except (ValueError, KeyError, OSError):
                        reason = "workspace_revoked"
                    if reason:
                        live.request_stop(reason)
                if now >= live.deadline:
                    live.request_stop("execution_timeout")

                root_code = process.root_exit_code() if root_code is None else root_code
                active = process.active_processes()
                if live.stop_reason and not stop_reason and active:
                    stop_reason = live.stop_reason
                    process.terminate()
                    stop_deadline = now + _DRAIN_SECONDS
                    process.close_stdin()
                if stop_deadline is not None and now >= stop_deadline and active:
                    self._finish(live.id, "unknown", "process_tree_did_not_stop", root_code, active, False)
                    break

                chunks = []
                for _ in range(16):
                    read = False
                    for stream in _STREAMS:
                        if stream not in open_streams:
                            continue
                        data = process.read(stream, LOG_CHUNK_BYTES)
                        if data is None:
                            open_streams.remove(stream)
                        elif data:
                            chunks.append((stream, data))
                            read = True
                    if not read:
                        break

                stdin_open = process.stdin_open
                facts = root_code, active, stdin_open, stop_reason
                if chunks or facts != previous_facts:
                    self._persist(live.id, chunks, *facts)
                    previous_facts = facts
                if active == 0 and root_code is not None:
                    if not open_streams:
                        state = "timed_out" if stop_reason == "execution_timeout" else "cancelled" if stop_reason else "exited"
                        self._finish(live.id, state, stop_reason, root_code, 0, True)
                        break
                    drain_deadline = drain_deadline or now + _DRAIN_SECONDS
                    if now >= drain_deadline and not chunks:
                        self._finish(live.id, "unknown", "output_not_finalized", root_code, 0, False)
                        break
                live.wake.wait(0.004 if chunks else 0.04)
                live.wake.clear()
        except Exception as exc:
            # Close the Job first even when SQLite no longer accepts writes.
            process.close_job()
            logger.warning("Local execution supervision failed for %s (%s)", live.id, type(exc).__name__)
            try:
                self._finish(live.id, "unknown", "supervision_or_storage_failed", root_code, None, False)
            except Exception as persistence_error:
                logger.warning("Could not persist final local Job state (%s)", type(persistence_error).__name__)
        finally:
            try:
                process.close()
            finally:
                live.done.set()
                with self._lock:
                    self._jobs.pop(live.id, None)

    def _persist(
        self, job_id: str, chunks: list[tuple[str, bytes]], root: int | None,
        active: int, stdin_open: bool, stop_reason: str | None,
    ) -> None:
        with self._lock, self._sessions() as db, db.begin():
            job = db.get(LocalExecutionJob, job_id)
            if job is None or job.engine_generation != self.generation or job.state not in ACTIVE_STATES:
                raise ExecutionError("The Job is no longer owned by this Sidecar generation.")
            job.root_exit_code, job.active_processes, job.stdin_open = root, active, stdin_open
            if stop_reason:
                job.state, job.reason = "stopping", stop_reason
            for stream, data in chunks:
                job.total_bytes += len(data)
                job.last_cursor += 1
                job.retained_bytes += len(data)
                db.add(LocalExecutionLog(
                    job_id=job_id, cursor=job.last_cursor, stream=stream, byte_end=job.total_bytes, data=data,
                ))
            if job.retained_bytes > _JOB_LOG_BYTES:
                db.flush()
                oldest = db.execute(select(LocalExecutionLog.cursor, LocalExecutionLog.byte_end).where(
                    LocalExecutionLog.job_id == job_id,
                    LocalExecutionLog.byte_end - func.length(LocalExecutionLog.data) < job.total_bytes - _JOB_LOG_BYTES,
                ).order_by(LocalExecutionLog.cursor.desc()).limit(1)).one()
                db.execute(delete(LocalExecutionLog).where(
                    LocalExecutionLog.job_id == job_id, LocalExecutionLog.cursor <= oldest.cursor,
                ))
                job.first_cursor = oldest.cursor + 1
                job.retained_bytes = job.total_bytes - oldest.byte_end
            self._sweep(db)

    def _finish(self, job_id, state, reason, root, active, finalized) -> None:
        with self._sessions() as db, db.begin():
            db.execute(update(LocalExecutionJob).where(
                LocalExecutionJob.id == job_id, LocalExecutionJob.engine_generation == self.generation,
                LocalExecutionJob.state.in_(ACTIVE_STATES),
            ).values(
                state=state, reason=reason, root_exit_code=root, active_processes=active,
                stdin_open=False, output_finalized=finalized, finished_at=_now_ms(),
            ))

    def _sweep(self, db: Session) -> None:
        now = time.monotonic()
        if now < self._next_sweep:
            return
        self._next_sweep = now + 10
        total = db.scalar(select(func.coalesce(func.sum(LocalExecutionJob.retained_bytes), 0)))
        oldest = _now_ms() - _LOG_TTL_MS
        for job in db.scalars(select(LocalExecutionJob).where(
            LocalExecutionJob.finished_at.is_not(None), LocalExecutionJob.retained_bytes > 0,
        ).order_by(LocalExecutionJob.finished_at)):
            if total <= _TOTAL_LOG_BYTES and job.finished_at >= oldest:
                break
            db.execute(delete(LocalExecutionLog).where(LocalExecutionLog.job_id == job.id))
            total -= job.retained_bytes
            job.first_cursor, job.retained_bytes = job.last_cursor + 1, 0
