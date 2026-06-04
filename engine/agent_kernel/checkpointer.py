from __future__ import annotations

import logging
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from engine.db import DB_PATH

logger = logging.getLogger("databox.agent_kernel.checkpointer")

_CHECKPOINTER_STACK = ExitStack()


def build_agent_kernel_checkpointer(
    path: str | Path | None = None,
    *,
    stack: ExitStack | None = None,
) -> Any:
    mode = os.environ.get("DATABOX_AGENT_KERNEL_CHECKPOINTER", "").strip().lower()
    if mode == "memory" or (os.environ.get("DATABOX_TESTING") == "1" and path is None):
        return InMemorySaver()

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning("langgraph-checkpoint-sqlite is not installed; falling back to in-memory LangGraph checkpoints.")
        return InMemorySaver()

    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    checkpoint_path = Path(path) if path is not None else DB_PATH.with_name("databox_agent_kernel_checkpoints.sqlite")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    active_stack = stack or _CHECKPOINTER_STACK
    checkpointer = active_stack.enter_context(SqliteSaver.from_conn_string(str(checkpoint_path)))
    setup = getattr(checkpointer, "setup", None)
    if callable(setup):
        setup()
    return checkpointer

