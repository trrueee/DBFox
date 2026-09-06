"""One ephemeral Tool-owned request across the Python/browser GPU boundary."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import secrets
import threading
import time
from uuid import uuid4

from . import contracts as c
from .mutations import decode_rgba
from .store import ShaderError, check_cancelled
from hashlib import sha256


@dataclass
class Executor:
    client_id: str
    counter: int
    epoch: str
    lease: str
    available: bool
    capabilities: c.Capabilities
    expires: float


@dataclass
class Pending:
    request: c.ComputeRequest
    epoch: str
    started: float
    deadline: float
    claimed: bool = False
    result: c.ComputeResult | None = None
    error: ShaderError | None = None


class ComputeBridge:
    def __init__(self, package_digest: str, *, deadline_seconds: float = 10, clock: Callable[[], float] = time.monotonic) -> None:
        self.package_digest = package_digest
        self.deadline_seconds = deadline_seconds
        self.clock = clock
        self.condition = threading.Condition()
        self.executor: Executor | None = None
        self.pending: Pending | None = None

    def _revoke(self, message: str) -> None:
        if self.pending is not None:
            self.pending.error = ShaderError("SHADER_EXECUTOR_UNAVAILABLE", message)
        if self.executor is not None:
            self.executor.available = False
            self.executor.expires = 0
        self.condition.notify_all()

    def attach(self, data: c.AttachInput) -> c.AttachResult:
        with self.condition:
            if data.package_digest != self.package_digest:
                raise ShaderError("SHADER_PACKAGE_MISMATCH", "Executor package identity does not match the active owner.")
            now = self.clock()
            current = self.executor
            if current is not None:
                if current.client_id == data.client_id and data.registration_counter <= current.counter:
                    raise ShaderError("SHADER_EPOCH_STALE", "Executor registration counter is not newer.")
                if current.client_id != data.client_id and current.expires > now:
                    raise ShaderError("SHADER_COMPUTE_BUSY", "Another executor holds the active lease.")
                self._revoke("Executor activation changed; old work is not replayed.")
            current = Executor(data.client_id, data.registration_counter, str(uuid4()), secrets.token_hex(32), data.available, data.capabilities, now + 5)
            self.executor = current
            return c.AttachResult(epoch=current.epoch, lease=current.lease, server_status="ready" if current.available else "unavailable")

    def _lease(self, data: c.LeaseInput) -> Executor:
        current = self.executor
        if current is None or data.epoch != current.epoch or not secrets.compare_digest(data.lease, current.lease) or data.registration_counter != current.counter:
            raise ShaderError("SHADER_EPOCH_STALE", "Executor lease is unknown or revoked.")
        if current.expires <= self.clock() or not current.available:
            self._revoke("Executor lease expired or became unavailable.")
            raise ShaderError("SHADER_EXECUTOR_UNAVAILABLE", "Executor lease is unavailable.")
        return current

    def next(self, data: c.LeaseInput) -> c.NextResult:
        with self.condition:
            current = self._lease(data)
            current.expires = self.clock() + 5
            pending = self.pending
            if pending is None or pending.error is not None:
                return c.NextResult(status="idle")
            if pending.epoch != current.epoch or pending.deadline <= self.clock():
                pending.error = ShaderError("SHADER_COMPUTE_TIMEOUT", "GPU request deadline expired.")
                self.condition.notify_all()
                return c.NextResult(status="idle")
            if pending.claimed:
                return c.NextResult(status="busy")
            pending.claimed = True
            remaining = max(1, min(10_000, int((pending.deadline-self.clock())*1000)))
            result = c.NextResult(status="request", request=pending.request.model_copy(update={"remaining_ms": remaining}))
            if len(c.encoded(result.model_dump(mode="json", exclude_none=True))) > 8_388_608:
                pending.error = ShaderError("SHADER_LIMIT", "GPU request transport budget exceeded.")
                self.condition.notify_all()
                raise pending.error
            return result

    def complete(self, data: c.CompleteInput) -> c.Accepted:
        with self.condition:
            self._lease(data)
            pending = self.pending
            if pending is None or pending.error is not None or pending.result is not None or not pending.claimed:
                raise ShaderError("SHADER_REQUEST_UNKNOWN", "GPU claim is unknown, completed, or revoked.")
            if data.package_digest != self.package_digest or pending.epoch != data.epoch or pending.deadline <= self.clock():
                raise ShaderError("SHADER_REQUEST_UNKNOWN", "GPU claim package, epoch, or deadline does not match.")
            request = pending.request
            for name in ("request_id", "claim", "invocation_id", "document_id", "version", "content_hash", "request_hash"):
                if getattr(data, name) != getattr(request, name):
                    raise ShaderError("SHADER_CLAIM_MISMATCH", "GPU claim does not match the authorized request.")
            if len(c.encoded(data.model_dump(mode="json", exclude_none=True))) > 1_048_576:
                raise ShaderError("SHADER_LIMIT", "GPU receipt exceeds its transport budget.")
            result = data.result
            if result.rendered:
                preview = request.snapshot.document.preview
                if not result.compiled or request.kind != "preview" or result.width != preview.width or result.height != preview.height or result.row_order != "bottom-left" or result.rgba_base64 is None:
                    raise ShaderError("SHADER_GPU_RESULT_INVALID", "Preview result dimensions, kind, or row layout do not match.")
                try:
                    decode_rgba(result.rgba_base64, preview.width, preview.height)
                except ValueError as exc:
                    raise ShaderError("SHADER_GPU_RESULT_INVALID", str(exc)) from exc
            elif any(value is not None for value in (result.width, result.height, result.rgba_base64, result.row_order)):
                raise ShaderError("SHADER_GPU_RESULT_INVALID", "Non-rendered results cannot include pixel fields.")
            try:
                c.validate_compute_evidence(request.snapshot.document, result, request.kind)
            except ValueError as exc:
                raise ShaderError("SHADER_GPU_RESULT_INVALID", str(exc)) from exc
            # Operational failures cannot masquerade as observed ESSL errors.
            if any(item.code in c.OPERATIONAL_ERRORS for item in result.diagnostics):
                pending.error = ShaderError("SHADER_GPU_UNAVAILABLE", "GPU execution failed; no successful preview was recorded.")
            else:
                pending.result = result
            self.condition.notify_all()
            return c.Accepted()

    def detach(self, data: c.DetachInput) -> c.Accepted:
        with self.condition:
            current = self.executor
            if current is None or current.epoch != data.epoch or not secrets.compare_digest(current.lease, data.lease):
                raise ShaderError("SHADER_EPOCH_STALE", "Cannot detach an unknown or superseded executor.")
            self._revoke("Executor detached; GPU work is not replayed.")
            return c.Accepted()

    def execute(self, invocation_id: str, revision: c.Revision, snapshot: c.Snapshot, kind: str, cancelled: Callable[[], bool]) -> tuple[c.ComputeResult, c.Capabilities, int, Callable[[], bool]]:
        with self.condition:
            check_cancelled(cancelled)
            current = self.executor
            now = self.clock()
            if current is None or not current.available or current.expires <= now:
                raise ShaderError("SHADER_EXECUTOR_UNAVAILABLE", "A visible active Shader executor is required.")
            if self.pending is not None:
                raise ShaderError("SHADER_COMPUTE_BUSY", "The Shader owner already has an active GPU request.")
            request_hash = sha256(c.encoded({"snapshot": snapshot.model_dump(mode="json"), "kind": kind, "invocation_id": invocation_id, "version": revision.version, "content_hash": revision.content_hash})).hexdigest()
            request = c.ComputeRequest(request_id=str(uuid4()), claim=secrets.token_hex(32), invocation_id=invocation_id, document_id=revision.document.id, version=revision.version, content_hash=revision.content_hash, request_hash=request_hash, remaining_ms=10_000, kind=kind, snapshot=snapshot)
            pending = Pending(request, current.epoch, now, now+self.deadline_seconds)
            self.pending = pending

            def commit_guard() -> bool:
                # Result handoff is not durable commit. Keep the exact activation
                # and deadline fence until the owner transaction checks it again.
                with self.condition:
                    check_cancelled(cancelled)
                    if self.executor is not current or not current.available or current.expires <= self.clock():
                        raise ShaderError("SHADER_EXECUTOR_UNAVAILABLE", "Executor changed before report commit.")
                    if self.clock() >= pending.deadline:
                        raise ShaderError("SHADER_COMPUTE_TIMEOUT", "GPU evidence deadline expired before commit.")
                    return False
            try:
                while True:
                    check_cancelled(cancelled)
                    now = self.clock()
                    if pending.error is not None:
                        raise pending.error
                    if current.expires <= now or self.executor is not current or not current.available:
                        raise ShaderError("SHADER_EXECUTOR_UNAVAILABLE", "Executor lease was lost during GPU work.")
                    if now >= pending.deadline:
                        raise ShaderError("SHADER_COMPUTE_TIMEOUT", "GPU request exceeded its ten-second deadline.")
                    if pending.result is not None:
                        return pending.result, current.capabilities, min(10_000, max(0, int((now-pending.started)*1000))), commit_guard
                    self.condition.wait(timeout=0.05)
            finally:
                self.pending = None
                self.condition.notify_all()
