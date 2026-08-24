"""Scoped production Runtime snapshots for capability-neutral verification."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def isolated_kernel_snapshot(storage_root: Path) -> Iterator[object]:
    """Install a capability-neutral production snapshot for one verification scope."""

    from engine.runtime_composition import (
        active_runtime_snapshot,
        initialize_runtime_snapshot,
        set_active_runtime_snapshot,
    )

    previous = active_runtime_snapshot()
    snapshot = initialize_runtime_snapshot(storage_root=storage_root)
    try:
        yield snapshot
    finally:
        set_active_runtime_snapshot(previous)
