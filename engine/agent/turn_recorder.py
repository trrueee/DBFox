"""Durable and live projection of one Provider Turn stream."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from engine.agent.control import LeaseAwareRunControl
from engine.agent.events import LiveStreamHub
from engine.agent.repositories.run import RunRepository
from engine.agent.run import RunPhase
from engine.agent.run_item import RunItemDelta, RunItemStatus, RunItemType
from engine.agent.session import SessionLease
from engine.agent.turn import TurnStreamError, TurnStreamItem, TurnStreamKind


@dataclass
class _StreamingMessageState:
    output_index: int
    phase: Literal["commentary", "final_answer"] | None
    text: str = ""
    live_revision: int = 0
    persisted_revision: int = 0
    flushed_bytes: int = 0
    last_flush: float = field(default_factory=time.monotonic)
    ended: bool = False


class RunTurnRecorder:
    """Own the message lifecycle and its short durable transactions."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        live_stream: LiveStreamHub,
    ) -> None:
        self._session_factory = session_factory
        self._live_stream = live_stream

    def publish(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        items: Iterable[TurnStreamItem],
        control: LeaseAwareRunControl,
    ) -> Iterable[TurnStreamItem]:
        messages: dict[str, _StreamingMessageState] = {}
        stream_completed = False
        try:
            for item in items:
                control.checkpoint()
                if item.kind is TurnStreamKind.ANSWER_START:
                    self.set_phase(lease, run_id, RunPhase.STREAMING_ANSWER)
                    if item.output_index is None:
                        raise TurnStreamError(
                            "Answer stream item is missing its output index"
                        )
                    state = _StreamingMessageState(
                        output_index=item.output_index,
                        phase=item.phase,
                    )
                    messages[item.item_id] = state
                    state.persisted_revision = 1
                    self._persist_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=state,
                        status=RunItemStatus.IN_PROGRESS,
                    )
                elif item.kind is TurnStreamKind.TOOL_CALL_START:
                    self.set_phase(lease, run_id, RunPhase.PREPARING_TOOL_CALL)
                elif item.kind is TurnStreamKind.ANSWER_DELTA:
                    delta_state = messages.get(item.item_id)
                    if delta_state is None or delta_state.ended:
                        raise TurnStreamError(
                            "Answer delta is outside its persisted message lifecycle"
                        )
                    content = item.content or ""
                    offset = len(delta_state.text)
                    delta_state.text += content
                    delta_state.live_revision += 1
                    self._live_stream.publish(
                        RunItemDelta(
                            session_id=lease.session_id,
                            run_id=run_id,
                            turn_id=turn_id,
                            item_id=(
                                f"message:{run_id}:{turn_id}:"
                                f"{delta_state.output_index}"
                            ),
                            item_type=RunItemType.MESSAGE,
                            field="content",
                            revision=delta_state.live_revision,
                            offset=offset,
                            content=content,
                        )
                    )
                    current_bytes = len(delta_state.text.encode("utf-8"))
                    if delta_state.text and (
                        current_bytes - delta_state.flushed_bytes >= 1024
                        or time.monotonic() - delta_state.last_flush >= 0.25
                    ):
                        delta_state.persisted_revision += 1
                        self._persist_message(
                            lease=lease,
                            run_id=run_id,
                            turn_id=turn_id,
                            state=delta_state,
                            status=RunItemStatus.IN_PROGRESS,
                        )
                        delta_state.flushed_bytes = current_bytes
                        delta_state.last_flush = time.monotonic()
                elif item.kind is TurnStreamKind.ANSWER_END:
                    ended_state = messages.get(item.item_id)
                    if ended_state is None or ended_state.ended:
                        raise TurnStreamError(
                            "Answer end is outside its persisted message lifecycle"
                        )
                    if item.message_status not in {"completed", "incomplete"}:
                        raise TurnStreamError(
                            "Answer end is missing its completed status"
                        )
                    ended_state.phase = item.phase
                    ended_state.ended = True
                    ended_state.persisted_revision += 1
                    self._persist_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=ended_state,
                        status=(
                            RunItemStatus.COMPLETED
                            if item.message_status == "completed"
                            else RunItemStatus.FAILED
                        ),
                    )
                yield item
            stream_completed = True
        finally:
            if not stream_completed:
                for state in messages.values():
                    if state.ended:
                        continue
                    state.ended = True
                    state.persisted_revision += 1
                    self._persist_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=state,
                        status=RunItemStatus.CANCELLED,
                    )

    def set_phase(
        self,
        lease: SessionLease,
        run_id: str,
        phase: RunPhase,
    ) -> None:
        with self._session_factory() as db:
            RunRepository(db).set_phase(lease=lease, run_id=run_id, phase=phase)
            db.commit()

    def _persist_message(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        state: _StreamingMessageState,
        status: RunItemStatus,
    ) -> None:
        with self._session_factory() as db:
            RunRepository(db).persist_turn_message(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                output_index=state.output_index,
                revision=state.persisted_revision,
                phase=state.phase,
                content=state.text,
                status=status,
            )
            db.commit()
