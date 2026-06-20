from __future__ import annotations

import os

from fastapi import APIRouter, Query

from engine.diagnostics.logs import (
    DEFAULT_MAX_LINES,
    collect_diagnostic_logs,
    diagnostic_log_paths,
)

router = APIRouter()


@router.get("/diagnostics/logs")
def get_diagnostic_logs(
    max_lines: int = Query(DEFAULT_MAX_LINES, ge=1, le=1000),
) -> dict[str, object]:
    return collect_diagnostic_logs(
        max_lines=max_lines,
        sources=diagnostic_log_paths(),
    )


@router.delete("/diagnostics/logs")
def clear_diagnostic_logs() -> dict[str, object]:
    cleared: list[str] = []
    for name, path in diagnostic_log_paths():
        if path.exists():
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.truncate(0)
                cleared.append(name)
            except OSError:
                pass
    return {"cleared": len(cleared) > 0, "sources_cleared": cleared}
