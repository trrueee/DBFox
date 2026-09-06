"""One activation-local Phaser request; no persisted queue, fallback or replay."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from uuid import uuid4

from . import contracts as c
from .store import GameError, Guard, request_hash


@dataclass
class Pending:
    request_id: str
    invocation_id: str
    revision: c.Revision
    input: c.PlaytestInput
    snapshot: dict[str, c.JsonValue]
    epoch: str
    deadline: float
    claim_id: str | None = None
    outcome: c.CompleteInput | None = None
    wake: threading.Event = field(default_factory=threading.Event)


class Bridge:
    LEASE_SECONDS = 5.0
    REQUEST_SECONDS = 20.0

    def __init__(self, package_digest: str) -> None:
        self.package_digest = package_digest
        self._lock = threading.RLock()
        self._attachment: c.Attachment | None = None
        self._client_id: str | None = None
        self._last_counter: dict[str, int] = {}
        self._expires = 0.0
        self._pending: Pending | None = None

    def attach(self, data: c.AttachInput) -> c.Attachment:
        with self._lock:
            if data.package_digest != self.package_digest:
                raise GameError("PACKAGE_MISMATCH", "Phaser executor package does not match this backend", 409)
            if data.registration_counter <= self._last_counter.get(data.client_id, 0):
                raise GameError("STALE_EXECUTOR", "Executor registration was already replaced", 409)
            if self._attachment is not None and self._expires > time.monotonic() and self._client_id != data.client_id:
                raise GameError("EXECUTOR_BUSY", "Another active Game executor owns this lease", 409)
            if data.client_id not in self._last_counter and len(self._last_counter) >= 128:
                raise GameError("EXECUTOR_BUDGET", "Executor registration budget exhausted for this activation", 409)
            if self._pending:
                self._pending.wake.set()
            self._last_counter[data.client_id] = data.registration_counter
            self._client_id = data.client_id
            self._attachment = c.Attachment(epoch=str(uuid4()), lease=str(uuid4()), registration_counter=data.registration_counter, available=data.available)
            self._expires = time.monotonic() + self.LEASE_SECONDS
            return self._attachment.model_copy()

    def _lease(self, data: c.Lease) -> c.Attachment:
        current = self._attachment
        if current is None or current.epoch != data.epoch or current.lease != data.lease or current.registration_counter != data.registration_counter or self._expires <= time.monotonic():
            raise GameError("STALE_EXECUTOR", "Game executor lease is no longer active", 409)
        return current

    def next(self, data: c.Lease) -> c.PollOutput:
        with self._lock:
            current = self._lease(data)
            self._expires = time.monotonic() + self.LEASE_SECONDS
            task = self._pending
            if not current.available or task is None or task.epoch != current.epoch or task.claim_id is not None:
                return c.PollOutput(status="idle")
            remaining = int((task.deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                return c.PollOutput(status="idle")
            task.claim_id = str(uuid4())
            request = c.ComputeRequest(request_id=task.request_id, invocation_id=task.invocation_id, game_id=task.revision.game.id, version=task.revision.version, source_hash=task.revision.content_hash, input_hash=request_hash("playtest", task.input), claim_id=task.claim_id, remaining_ms=min(remaining, 20000), input=task.input, snapshot=task.snapshot)
            return c.PollOutput(status="request", request=request)

    def complete(self, data: c.CompleteInput) -> c.Acknowledged:
        with self._lock:
            self._lease(data)
            task = self._pending
            if data.package_digest != self.package_digest or task is None or task.epoch != data.epoch:
                raise GameError("STALE_REQUEST", "Phaser result does not belong to the active request", 409)
            if task.claim_id is None:
                raise GameError("STALE_REQUEST", "Phaser request has not been claimed", 409)
            expected = c.Proof(request_id=task.request_id, invocation_id=task.invocation_id, game_id=task.revision.game.id, version=task.revision.version, source_hash=task.revision.content_hash, input_hash=request_hash("playtest", task.input), claim_id=task.claim_id)
            if c.Proof.model_validate(data.model_dump(include=set(c.Proof.model_fields))) != expected or task.outcome is not None or time.monotonic() >= task.deadline:
                raise GameError("STALE_REQUEST", "Phaser result proof, claim or deadline does not match", 409)
            task.outcome = data.model_copy(deep=True)
            task.wake.set()
            return c.Acknowledged(accepted=True)

    def detach(self, data: c.Lease) -> c.Acknowledged:
        with self._lock:
            self._lease(data)
            self._attachment = None
            self._expires = 0
            if self._pending:
                self._pending.wake.set()
            return c.Acknowledged(accepted=True)

    def request(self, revision: c.Revision, data: c.PlaytestInput, invocation_id: str, snapshot: dict[str, c.JsonValue], guard: Guard) -> Pending:
        guard()
        if len(c.encoded(snapshot)) + len(c.encoded(data.data())) + 2048 > 8 * 1024 * 1024:
            raise GameError("SNAPSHOT_BUDGET", "Phaser snapshot exceeds its byte budget")
        with self._lock:
            current = self._attachment
            if current is None or not current.available or self._expires <= time.monotonic():
                raise GameError("ENGINE_UNAVAILABLE", "No active Phaser executor is available; open the visible DBFox workspace", 409)
            if self._pending is not None:
                raise GameError("EXECUTOR_BUSY", "A Game playtest is already in progress", 409)
            task = Pending(str(uuid4()), invocation_id, revision, data, snapshot, current.epoch, time.monotonic() + self.REQUEST_SECONDS)
            self._pending = task
            return task

    def check(self, task: Pending) -> None:
        with self._lock:
            current = self._attachment
            if self._pending is not task or current is None or current.epoch != task.epoch or not current.available or self._expires <= time.monotonic():
                raise GameError("STALE_EXECUTOR", "Phaser activation changed or disconnected before commit", 409)
            if time.monotonic() >= task.deadline:
                raise GameError("DEADLINE_EXCEEDED", "Game playtest deadline expired", 409)

    def wait(self, task: Pending, guard: Guard) -> c.SimulationReport:
        while True:
            guard()
            self.check(task)
            with self._lock:
                outcome = task.outcome
            if outcome is not None:
                if outcome.report is None:
                    raise GameError(outcome.error or "ENGINE_FAILURE", "Phaser could not complete the requested playtest", 409)
                return outcome.report
            task.wake.wait(.05)

    def finish(self, task: Pending) -> None:
        with self._lock:
            if self._pending is task:
                self._pending = None
            task.wake.set()
