"""Short-lived requests to present an existing Artifact in the local Workbench."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock
from time import monotonic, time
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.agent.artifact import Artifact

WorkbenchPresentationOutcome = Literal["opened", "not_opened", "unconfirmed"]


class WorkbenchPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str
    conversation_id: str
    project_id: str
    artifact_id: str
    title: str
    expires_at_ms: int


class WorkbenchPresentationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["opened", "not_opened"]


@dataclass(slots=True)
class _PendingPresentation:
    presentation: WorkbenchPresentation
    deadline: float
    completed: Event = field(default_factory=Event)
    claimed: bool = False
    outcome: WorkbenchPresentationOutcome | None = None


class WorkbenchPresentationBroker:
    """One delivery per live ToolInvocation, with no reconnect replay."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingPresentation] = {}
        self._lock = Lock()

    def present(
        self,
        *,
        artifact: Artifact,
        invocation_id: str,
        project_id: str,
        cancelled: Callable[[], bool],
        deadline: float | None,
    ) -> WorkbenchPresentationOutcome:
        started = monotonic()
        expires = min(started + 4.0, deadline) if deadline is not None else started + 4.0
        if expires <= started or cancelled():
            return "not_opened"
        presentation = WorkbenchPresentation(
            invocation_id=invocation_id,
            conversation_id=artifact.session_id,
            project_id=project_id,
            artifact_id=artifact.id,
            title=artifact.title[:500],
            expires_at_ms=int((time() + expires - started) * 1000),
        )
        pending = _PendingPresentation(presentation=presentation, deadline=expires)
        with self._lock:
            if invocation_id in self._pending:
                return "unconfirmed"
            self._pending[invocation_id] = pending
        try:
            while not cancelled():
                remaining = expires - monotonic()
                if remaining <= 0 or pending.completed.wait(min(0.2, remaining)):
                    break
        finally:
            with self._lock:
                del self._pending[invocation_id]
        return pending.outcome or ("unconfirmed" if pending.claimed else "not_opened")

    def cancel(self, invocation_id: str) -> None:
        with self._lock:
            pending = self._pending.get(invocation_id)
            if pending is not None:
                pending.completed.set()

    def claim(self, conversation_id: str, invocation_id: str) -> WorkbenchPresentation | None:
        with self._lock:
            pending = self._current(conversation_id, invocation_id)
            if pending is None or pending.claimed:
                return None
            pending.claimed = True
            return pending.presentation

    def acknowledge(
        self,
        conversation_id: str,
        invocation_id: str,
        receipt: WorkbenchPresentationReceipt,
    ) -> bool:
        with self._lock:
            pending = self._current(conversation_id, invocation_id)
            if pending is None or not pending.claimed:
                return False
            pending.outcome = receipt.outcome
            pending.completed.set()
            return True

    def _current(self, conversation_id: str, invocation_id: str) -> _PendingPresentation | None:
        pending = self._pending.get(invocation_id)
        if (pending is None or pending.presentation.conversation_id != conversation_id
            or pending.deadline <= monotonic() or pending.completed.is_set()):
            return None
        return pending
