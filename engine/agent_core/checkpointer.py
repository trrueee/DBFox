from __future__ import annotations

import logging
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from engine.db import DB_PATH

logger = logging.getLogger("dbfox.agent_core.checkpointer")

_CHECKPOINTER_STACK = ExitStack()
_SHARED_MEMORY_SAVER = None


def build_agent_core_checkpointer(
    path: str | Path | None = None,
    *,
    stack: ExitStack | None = None,
) -> Any:
    mode = os.environ.get("DBFOX_AGENT_CORE_CHECKPOINTER", "").strip().lower()
    if mode == "memory" or (os.environ.get("DBFOX_TESTING") == "1" and path is None):
        global _SHARED_MEMORY_SAVER
        if _SHARED_MEMORY_SAVER is None:
            _SHARED_MEMORY_SAVER = InMemorySaver()
        return _SHARED_MEMORY_SAVER

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning("langgraph-checkpoint-sqlite is not installed; falling back to in-memory LangGraph checkpoints.")
        return InMemorySaver()

    checkpoint_path = Path(path) if path is not None else DB_PATH.with_name("dbfox_agent_core_checkpoints.sqlite")
    
    current_version = "v1"
    version_file = checkpoint_path.with_name(f"{checkpoint_path.name}.version")
    should_reset = False
    
    if checkpoint_path.exists():
        if version_file.exists():
            try:
                saved_version = version_file.read_text(encoding="utf-8").strip()
                if saved_version != current_version:
                    logger.warning("Checkpointer version mismatch: expected %s, got %s. Resetting checkpoint database.", current_version, saved_version)
                    should_reset = True
            except Exception as e:
                logger.error("Failed to read checkpointer version: %s. Resetting.", e)
                should_reset = True
        else:
            logger.warning("Checkpointer version file missing. Resetting checkpoint database to ensure compatibility.")
            should_reset = True

    if should_reset:
        try:
            for suffix in ("", "-wal", "-shm", "-journal"):
                p = checkpoint_path.with_name(f"{checkpoint_path.name}{suffix}")
                if p.exists():
                    p.unlink()
            if version_file.exists():
                version_file.unlink()
        except Exception as e:
            logger.error("Failed to delete stale checkpoint database: %s", e)

    try:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(current_version, encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write checkpointer version: %s", e)

    active_stack = stack or _CHECKPOINTER_STACK
    checkpointer = active_stack.enter_context(SqliteSaver.from_conn_string(str(checkpoint_path)))
    setup = getattr(checkpointer, "setup", None)
    if callable(setup):
        setup()
    return checkpointer

