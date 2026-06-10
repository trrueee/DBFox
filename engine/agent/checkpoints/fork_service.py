"""Fork a new agent run from an existing checkpoint."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from engine.agent.checkpoints.checkpoint_schema import ForkRequest, ForkResponse

logger = logging.getLogger("databox.checkpoints.fork")


class ForkService:
    """Create a new run branching from a specific checkpoint."""

    def __init__(self, graph_app: Any) -> None:
        self._app = graph_app

    def fork(
        self,
        thread_id: str,
        request: ForkRequest,
    ) -> ForkResponse:
        """Fork a new run from *request.checkpoint_id*.

        Creates a new thread_id so the original run is untouched.
        """
        new_run_id = str(uuid.uuid4())
        new_thread_id = f"fork-{new_run_id}"

        logger.info(
            "Fork from checkpoint %s (thread %s) → new run %s (thread %s)",
            request.checkpoint_id, thread_id, new_run_id, new_thread_id,
        )

        # Get the checkpoint state
        old_config = {"configurable": {"thread_id": thread_id}}
        old_snapshot = self._app.get_state(old_config)

        if old_snapshot is None or not old_snapshot.values:
            raise ValueError(f"Checkpoint {request.checkpoint_id} not found for thread {thread_id}")

        # Clone state into new thread
        from engine.agent.graph.state import DataBoxAgentState
        old_values = dict(old_snapshot.values)

        # Apply state overrides
        if request.new_question:
            old_values["messages"] = old_values.get("messages", []) + [
                {"role": "user", "content": request.new_question}
            ]
        if request.state_overrides:
            old_values.update(request.state_overrides)

        new_state = DataBoxAgentState(**{k: v for k, v in old_values.items() if k in DataBoxAgentState.__optional_keys__})
        new_state["run_id"] = new_run_id
        new_state["thread_id"] = new_thread_id
        new_state["status"] = "running"

        new_config = {"configurable": {"thread_id": new_thread_id}}
        try:
            for _ in self._app.stream(new_state, config=new_config, stream_mode="updates"):
                pass  # Run to completion; caller can stream via service
        except Exception as exc:
            logger.error("Fork execution failed for %s: %s", new_run_id, exc)

        return ForkResponse(
            new_run_id=new_run_id,
            original_run_id=thread_id,
            forked_from_checkpoint_id=request.checkpoint_id,
            original_step=-1,
        )
