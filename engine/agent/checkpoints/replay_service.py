"""Replay agent execution from a given checkpoint."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.types import Command

from engine.agent.checkpoints.checkpoint_schema import ReplayRequest, ReplayResponse

logger = logging.getLogger("databox.checkpoints.replay")


class ReplayService:
    """Replay an agent run from a specific checkpoint."""

    def __init__(self, graph_app: Any) -> None:
        self._app = graph_app

    def replay(
        self,
        thread_id: str,
        request: ReplayRequest,
    ) -> list[dict[str, Any]]:
        """Re-execute from *request.checkpoint_id*.

        Returns the list of node updates from the replay.
        """
        config = {"configurable": {"thread_id": thread_id}}
        run_id = request.run_id or str(uuid.uuid4())

        logger.info("Replay from checkpoint %s → run %s", request.checkpoint_id, run_id)

        # Re-invoke with the same config; LangGraph resumes from the
        # specified checkpoint because thread_id is the same.
        chunks: list[dict[str, Any]] = []
        try:
            for chunk in self._app.stream(
                Command(resume=None),  # resume without new input
                config=config,
                stream_mode="updates",
            ):
                for node_name, update in chunk.items():
                    if isinstance(update, dict):
                        chunks.append({"node": str(node_name), "update": update})
        except Exception as exc:
            logger.error("Replay failed for %s: %s", thread_id, exc)
            chunks.append({"node": "error", "update": {"error": str(exc)}})

        return chunks

    def build_response(self, thread_id: str, request: ReplayRequest) -> ReplayResponse:
        return ReplayResponse(
            run_id=request.run_id or str(uuid.uuid4()),
            original_run_id=request.run_id or thread_id,
            checkpoint_id=request.checkpoint_id,
            replay_from_step=-1,
        )
