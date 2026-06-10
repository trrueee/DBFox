"""Service for listing and inspecting LangGraph checkpoints."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

from engine.agent.checkpoints.checkpoint_schema import (
    AgentCheckpointSnapshot,
    CheckpointListResponse,
)

logger = logging.getLogger("databox.checkpoints.service")


class CheckpointService:
    """List and query checkpoints for a run."""

    def __init__(self, graph_app: Any) -> None:
        """*graph_app* is a compiled LangGraph StateGraph."""
        self._app = graph_app

    def list_checkpoints(
        self,
        thread_id: str,
        run_id: str,
        limit: int = 50,
    ) -> CheckpointListResponse:
        """Return all checkpoints for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        snapshots: list[AgentCheckpointSnapshot] = []

        try:
            history = list(self._app.get_state_history(config, limit=limit))
        except Exception as exc:
            logger.warning("Failed to get state history for %s: %s", thread_id, exc)
            return CheckpointListResponse(run_id=run_id, thread_id=thread_id)

        for i, snapshot in enumerate(history):
            values = dict(snapshot.values) if isinstance(snapshot.values, dict) else {}
            metadata = getattr(snapshot, "metadata", {}) or {}
            created_at = str(metadata.get("timestamp", "")) or datetime.now(timezone.utc).isoformat()

            # Build next nodes
            next_nodes = list(snapshot.next) if snapshot.next else []

            # Detect interrupts
            interrupts = getattr(snapshot, "interrupts", None)
            has_interrupt = bool(interrupts)

            snapshots.append(
                AgentCheckpointSnapshot(
                    checkpoint_id=getattr(snapshot, "id", f"ckpt-{i}"),
                    thread_id=thread_id,
                    run_id=run_id,
                    created_at=created_at,
                    step=i,
                    next_nodes=next_nodes,
                    has_interrupt=has_interrupt,
                    state_summary={
                        "status": values.get("status", "unknown"),
                        "step_count": values.get("step_count", 0),
                        "has_schema": bool(values.get("schema_context")),
                        "has_sql": bool(values.get("sql")),
                        "has_execution": bool(values.get("execution")),
                        "has_answer": bool(values.get("answer")),
                    },
                )
            )

        return CheckpointListResponse(
            run_id=run_id,
            thread_id=thread_id,
            checkpoints=snapshots,
            total=len(snapshots),
        )

    def get_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
    ) -> AgentCheckpointSnapshot | None:
        """Get a specific checkpoint."""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = self._app.get_state(config)
        except Exception:
            return None

        if snapshot is None:
            return None

        values = dict(snapshot.values) if isinstance(snapshot.values, dict) else {}
        return AgentCheckpointSnapshot(
            checkpoint_id=checkpoint_id,
            thread_id=thread_id,
            run_id=str(values.get("run_id", "")),
            has_interrupt=bool(getattr(snapshot, "interrupts", None)),
            state_summary={
                "status": values.get("status", "unknown"),
                "step_count": values.get("step_count", 0),
                "has_schema": bool(values.get("schema_context")),
                "has_sql": bool(values.get("sql")),
            },
        )
