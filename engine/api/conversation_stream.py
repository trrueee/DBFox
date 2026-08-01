from __future__ import annotations

import queue
import threading
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from engine.agent.events import COMMIT_NOTIFICATIONS, LiveStreamGap, RuntimeEvent
from engine.agent.loop import LIVE_STREAM_HUB
from engine.agent.repositories.events import EventHistoryGap, EventRepository
from engine.agent.run_item import RunItemDelta
from engine.db import SessionLocal, get_db
from engine.json_codec import dumps as json_dumps
from engine.models import AgentSession


router = APIRouter()


@router.get(
    "/conversations/{conversation_id}/events",
    response_model=list[RuntimeEvent],
)
def list_conversation_events(
    conversation_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1_000),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    aggregate = db.get(AgentSession, conversation_id)
    if aggregate is None or aggregate.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND"})
    try:
        events = EventRepository(db).list(
            conversation_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except EventHistoryGap as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONVERSATION_SNAPSHOT_REQUIRED",
                "floor_sequence": exc.floor_sequence,
                "current_sequence": exc.current_sequence,
            },
        ) from exc
    return [item.model_dump(mode="json") for item in events]


@router.get("/conversations/{conversation_id}/stream")
def stream_conversation(
    conversation_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
) -> StreamingResponse:
    with SessionLocal() as db:
        aggregate = db.get(AgentSession, conversation_id)
        if aggregate is None or aggregate.deleted_at is not None:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND"})
    last_event_id = request.headers.get("last-event-id", "").strip()
    if last_event_id.isdigit():
        after_sequence = max(after_sequence, int(last_event_id))
    with SessionLocal() as db:
        try:
            EventRepository(db).list(
                conversation_id,
                after_sequence=after_sequence,
                limit=1,
            )
        except EventHistoryGap as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONVERSATION_SNAPSHOT_REQUIRED",
                    "floor_sequence": exc.floor_sequence,
                    "current_sequence": exc.current_sequence,
                },
            ) from exc
    return StreamingResponse(
        conversation_stream(conversation_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def conversation_stream(session_id: str, after_sequence: int) -> Iterator[str]:
    commit_subscription = COMMIT_NOTIFICATIONS.subscribe(session_id)
    live_subscription = LIVE_STREAM_HUB.subscribe_session(session_id)
    signals: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=512)
    stopped = threading.Event()
    commit_pending = threading.Event()
    stream_gap = threading.Event()

    def forward_commits() -> None:
        while not stopped.is_set():
            value = commit_subscription.receive(timeout=1.0)
            if value is None or commit_pending.is_set():
                continue
            commit_pending.set()
            try:
                signals.put_nowait(("commit", value))
            except queue.Full:
                commit_pending.clear()

    def forward_live() -> None:
        while not stopped.is_set():
            try:
                value = live_subscription.receive(timeout=1.0)
            except LiveStreamGap:
                stream_gap.set()
                try:
                    signals.put_nowait(("gap", None))
                except queue.Full:
                    pass
                return
            if value is not None:
                try:
                    signals.put_nowait(("live", value))
                except queue.Full:
                    stream_gap.set()
                    return

    threads = [
        threading.Thread(target=forward_commits, daemon=True),
        threading.Thread(target=forward_live, daemon=True),
    ]
    for thread in threads:
        thread.start()
    cursor = after_sequence
    try:
        while True:
            try:
                with SessionLocal() as db:
                    events = EventRepository(db).list(
                        session_id,
                        after_sequence=cursor,
                        limit=500,
                    )
            except EventHistoryGap:
                return
            for event in events:
                cursor = event.sequence
                yield sse_event(
                    event.event_type.value,
                    event.model_dump(mode="json"),
                    event_id=str(cursor),
                )
            if stream_gap.is_set():
                return
            try:
                kind, value = signals.get(timeout=15.0)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if kind == "live":
                if not isinstance(value, RunItemDelta):
                    raise RuntimeError("Live stream emitted an invalid delta")
                yield sse_event("run.item.delta", value.model_dump(mode="json"))
            elif kind == "gap":
                return
            elif kind == "commit":
                commit_pending.clear()
    finally:
        stopped.set()
        commit_subscription.close()
        live_subscription.close()
        for thread in threads:
            thread.join(timeout=1.25)


def sse_event(event_type: str, payload: object, event_id: str | None = None) -> str:
    encoded = json_dumps(payload)
    identity = f"id: {event_id}\n" if event_id else ""
    return f"{identity}event: {event_type}\ndata: {encoded}\n\n"
